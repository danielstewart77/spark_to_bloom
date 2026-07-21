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

    root.TerminalRouting = {pickReattachTarget: pickReattachTarget, isActive: isActive};
})(typeof globalThis !== "undefined" ? globalThis : this);
