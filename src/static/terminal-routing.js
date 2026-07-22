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

    root.TerminalRouting = {
        pickReattachTarget: pickReattachTarget,
        isActive: isActive,
        retryDelayMs: retryDelayMs,
    };
})(typeof globalThis !== "undefined" ? globalThis : this);
