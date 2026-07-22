/* Reattach routing rules for the web terminal.
 *
 * Run by tests/test_terminal_routing.py. Every case here is a shape that
 * actually broke: tiles adopting each other's conversations, labels
 * following the wrong session, and a live session declared dead because
 * its socket blinked.
 */
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// The module is a browser script, not an ES module — evaluate it the way a
// <script> tag would, against globalThis.
new Function(readFileSync(join(here, "..", "..", "src", "static", "terminal-routing.js"), "utf8"))();
const {pickReattachTarget, isActive, retryDelayMs, contrastText} = globalThis.TerminalRouting;

const tests = {
    "a live session is retried, not replaced"() {
        const rows = [{id: "a", status: "running"}];
        assert.deepEqual(pickReattachTarget(rows, {deadId: "a", openIds: ["a"]}), {action: "retry"});
    },

    "an idle session still counts as live"() {
        const rows = [{id: "a", status: "idle"}];
        assert.equal(pickReattachTarget(rows, {deadId: "a", openIds: []}).action, "retry");
    },

    "a rotation successor is adopted by lineage"() {
        const rows = [
            {id: "a", status: "closed"},
            {id: "b", status: "running", rotated_from: "a"},
        ];
        const target = pickReattachTarget(rows, {deadId: "a", openIds: ["a"]});
        assert.equal(target.action, "successor");
        assert.equal(target.session.id, "b");
    },

    "a sibling session on the same mind is NEVER adopted"() {
        // The exact bug: two terminals open, one drops, and it grabs the
        // other one's conversation along with its name and colour.
        const rows = [
            {id: "hex", status: "closed", mind_id: "skippy"},
            {id: "ada-proxy", status: "running", mind_id: "skippy"},
        ];
        assert.deepEqual(
            pickReattachTarget(rows, {deadId: "hex", openIds: ["hex", "ada-proxy"]}),
            {action: "wait"},
        );
    },

    "a successor already open in another tile is left alone"() {
        const rows = [
            {id: "a", status: "closed"},
            {id: "b", status: "running", rotated_from: "a"},
        ];
        assert.equal(
            pickReattachTarget(rows, {deadId: "a", openIds: ["a", "b"]}).action,
            "wait",
        );
    },

    "a closed successor is not adopted"() {
        const rows = [
            {id: "a", status: "closed"},
            {id: "b", status: "closed", rotated_from: "a"},
        ];
        assert.equal(pickReattachTarget(rows, {deadId: "a", openIds: []}).action, "wait");
    },

    "lineage pointing at a different session does not match"() {
        const rows = [
            {id: "a", status: "closed"},
            {id: "b", status: "running", rotated_from: "someone-else"},
        ];
        assert.equal(pickReattachTarget(rows, {deadId: "a", openIds: []}).action, "wait");
    },

    "retry wins over an equally valid successor"() {
        // If the original is still alive, the conversation never moved.
        const rows = [
            {id: "a", status: "running"},
            {id: "b", status: "running", rotated_from: "a"},
        ];
        assert.equal(pickReattachTarget(rows, {deadId: "a", openIds: []}).action, "retry");
    },

    "empty and malformed inputs wait rather than guess"() {
        assert.equal(pickReattachTarget([], {deadId: "a", openIds: []}).action, "wait");
        assert.equal(pickReattachTarget(null, {deadId: "a", openIds: []}).action, "wait");
        assert.equal(pickReattachTarget([{id: "a", status: "running"}], {}).action, "wait");
        assert.equal(pickReattachTarget([null, undefined], {deadId: "a"}).action, "wait");
    },

    "retries back off and cap instead of spinning"() {
        assert.equal(retryDelayMs(1), 500);
        assert.equal(retryDelayMs(2), 1000);
        assert.equal(retryDelayMs(3), 2000);
        // A mind that refuses every handshake must settle at the cap, not
        // keep reconnecting several times a second.
        assert.equal(retryDelayMs(20), 8000);
        // Garbage in still yields a real wait.
        assert.equal(retryDelayMs(0), 500);
        assert.equal(retryDelayMs(undefined), 500);
    },

    "contrastText picks dark ink on light session colors"() {
        assert.equal(contrastText("#ffffff"), "#0b1724");
        assert.equal(contrastText("#ffce42"), "#0b1724");
        assert.equal(contrastText("#d8dee4"), "#0b1724");
    },

    "contrastText picks light ink on dark session colors"() {
        assert.equal(contrastText("#0b1724"), "#f4f8fb");
        assert.equal(contrastText("#e05c8a"), "#f4f8fb");
        assert.equal(contrastText("#3d5266"), "#f4f8fb");
    },

    "contrastText falls back to the neutral ink on garbage"() {
        // Painted headers and cards call this with whatever the label
        // store holds — an empty label must not paint black-on-black.
        assert.equal(contrastText(""), "#dce8f0");
        assert.equal(contrastText(null), "#dce8f0");
        assert.equal(contrastText("red"), "#dce8f0");
        assert.equal(contrastText("#12345"), "#dce8f0");
    },

    "isActive classifies the statuses the rail renders"() {
        assert.equal(isActive({status: "RUNNING"}), true);
        assert.equal(isActive({status: "idle"}), true);
        assert.equal(isActive({status: "closed"}), false);
        assert.equal(isActive({}), false);
        assert.equal(isActive(null), false);
    },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
    try {
        fn();
        console.log("ok - " + name);
    } catch (err) {
        failed++;
        console.error("FAIL - " + name + "\n  " + err.message);
    }
}
console.log(`\n${Object.keys(tests).length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
