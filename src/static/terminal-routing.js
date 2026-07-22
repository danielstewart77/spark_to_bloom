/* Reattach routing for the web terminal.
 *
 * When a terminal tile's socket drops it has to decide what to reconnect
 * to. Getting this wrong is not cosmetic: the previous rule was "any live
 * session on the same mind", so with two tiles open the reconnecting one
 * adopted its neighbour's conversation, took its neighbour's name and
 * colour with it, and left the neighbour blank.
 *
 * The rules, in order:
 *   1. The same session, if it is still live. The pty now outlives the
 *      socket, so this is the ordinary case — a dropped connection, not a
 *      dead conversation.
 *   2. The session that rotation created to replace it, identified by
 *      recorded lineage (rotated_from) and not by proximity.
 *   3. Nothing. Waiting beats stealing.
 *
 * A session another tile already has open is never a candidate.
 */
(function (root) {
    "use strict";

    var ACTIVE_STATUSES = ["running", "idle"];

    function isActive(row) {
        return ACTIVE_STATUSES.indexOf(String(row && row.status || "").toLowerCase()) !== -1;
    }

    /**
     * @param {Array} rows      session rows from /api/terminal/sessions
     * @param {Object} opts     {deadId, openIds}
     * @returns {{action: "retry"|"successor"|"wait", session?: Object}}
     */
    function pickReattachTarget(rows, opts) {
        var list = Array.isArray(rows) ? rows : [];
        var deadId = (opts && opts.deadId) || "";
        var openIds = (opts && opts.openIds) || [];
        if (!deadId) return {action: "wait"};

        var i;
        for (i = 0; i < list.length; i++) {
            if (list[i] && list[i].id === deadId && isActive(list[i])) {
                return {action: "retry"};
            }
        }
        for (i = 0; i < list.length; i++) {
            var row = list[i];
            if (!row || row.id === deadId) continue;
            if (!row.rotated_from || row.rotated_from !== deadId) continue;
            if (!isActive(row)) continue;
            // Another tile is already driving this one — adopting it would
            // put two terminals on one conversation.
            if (openIds.indexOf(row.id) !== -1) continue;
            return {action: "successor", session: row};
        }
        return {action: "wait"};
    }

    /**
     * Delay before retrying an attach to the same session, in ms.
     *
     * The first retry is quick — the common case is a dropped socket over
     * a live pty, and waiting there is felt. Repeated failures mean the
     * attach itself is being refused, so the interval grows and caps
     * rather than spinning at the speed of the round trip.
     *
     * @param {number} attempt  1 for the first retry after a live socket
     * @returns {number} ms to wait
     */
    function retryDelayMs(attempt) {
        var n = Math.max(1, Math.floor(attempt) || 1);
        return Math.min(500 * Math.pow(2, n - 1), 8000);
    }

    /**
     * Readable ink color against an arbitrary swatch background, by
     * perceived luminance. Shared by the focused tile's full-bar header
     * and the rail's painted picker cards, so both surfaces flip their
     * text the same way for the same session color.
     *
     * @param {string} hex  "#rrggbb"
     * @returns {string} a dark or light ink hex; a neutral default for
     *                   anything that isn't a 6-digit hex color
     */
    function contrastText(hex) {
        var c = String(hex || "").replace("#", "");
        if (!/^[0-9a-fA-F]{6}$/.test(c)) return "#dce8f0";
        var r = parseInt(c.slice(0, 2), 16);
        var g = parseInt(c.slice(2, 4), 16);
        var b = parseInt(c.slice(4, 6), 16);
        var lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        return lum > 0.6 ? "#0b1724" : "#f4f8fb";
    }

    /**
     * The slice of xterm's helper textarea that Enter has to forward by
     * hand, given xterm's own composition state.
     *
     * Mobile keyboards type into that textarea through IME compositions,
     * and xterm does not clear it between words — it holds the whole line
     * and each composition is sent as it ends, from its own start offset
     * to the end of the box. So by the time Enter arrives, everything up
     * to the open composition's start is already down the wire. Forwarding
     * the whole box (the first cut of the mobile-Enter fix) resends the
     * entire paragraph and the pty shows it twice.
     *
     * Nothing is owed when no composition is open or in flight: xterm has
     * already sent it all. When one is, xterm is about to either drop it
     * (Enter finalizes with commit=false) or slice it against a stale end
     * offset, so this is the text that would otherwise be lost.
     *
     * @param {Object} state  xterm's composition state:
     *                        {composing, flushPending, start, alreadySent}
     * @param {string} value  the helper textarea's current value
     * @returns {string} the text to send before the carriage return
     */
    function pendingImeText(state, value) {
        var text = String(value == null ? "" : value);
        if (!state || !text) return "";
        if (!state.composing && !state.flushPending) return "";
        // Text the non-composition path sent after the composition
        // recorded its start offset sits between the two; xterm applies
        // the same correction when it flushes.
        var start = (state.start || 0) + String(state.alreadySent || "").length;
        if (!(start >= 0) || start >= text.length) return "";
        return text.slice(start);
    }

    root.TerminalRouting = {
        pickReattachTarget: pickReattachTarget,
        isActive: isActive,
        retryDelayMs: retryDelayMs,
        contrastText: contrastText,
        pendingImeText: pendingImeText,
    };
})(typeof globalThis !== "undefined" ? globalThis : this);
