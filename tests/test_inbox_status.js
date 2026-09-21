"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { applyInboxStatus } = require(
  path.join(__dirname, "..", "chat_app", "renderer", "inbox_status.js")
);

describe("applyInboxStatus", () => {
  it("keeps pending-chat completion on the restart poll before advancing the cursor", () => {
    const pending = {
      historyRev: 4,
      chatRevs: { "chat-1": 4 },
      bridgeId: "bridge-old",
      chatId: "chat-1",
      pendingChatId: "chat-1",
    };
    const restartPoll = {
      history_rev: 5,
      bridge_id: "bridge-new",
      chat_revs: { "chat-1": 5 },
      changed_chat_ids: ["chat-1"],
      completed_chat_ids: ["chat-1"],
      assistant_appended: 1,
    };

    const restart = applyInboxStatus(pending, restartPoll);
    assert.equal(restart.resync, true);
    assert.deepEqual(restart.completedChatIds, ["chat-1"]);
    assert.equal(restart.completedPending, true);
    assert.equal(restart.historyRev, 5);

    const followPoll = {
      history_rev: 5,
      bridge_id: "bridge-new",
      chat_revs: { "chat-1": 5 },
      changed_chat_ids: [],
      completed_chat_ids: [],
      assistant_appended: 0,
    };
    const follow = applyInboxStatus(
      {
        ...pending,
        historyRev: restart.historyRev,
        chatRevs: restart.chatRevs,
        bridgeId: restart.bridgeId,
      },
      followPoll
    );
    assert.equal(follow.resync, false);
    assert.deepEqual(follow.completedChatIds, []);
    assert.equal(follow.completedPending, false);
  });

  it("does not treat a user-only history bump as request completion", () => {
    const pending = {
      historyRev: 4,
      chatRevs: { "chat-1": 4 },
      bridgeId: "bridge-a",
      chatId: "chat-1",
      pendingChatId: "chat-1",
    };
    const userOnly = applyInboxStatus(pending, {
      history_rev: 5,
      bridge_id: "bridge-a",
      chat_revs: { "chat-1": 5 },
      changed_chat_ids: ["chat-1"],
      completed_chat_ids: [],
      appended_chat_ids: [],
      assistant_appended: 0,
    });
    assert.equal(userOnly.resync, false);
    assert.deepEqual(userOnly.changedChatIds, ["chat-1"]);
    assert.deepEqual(userOnly.completedChatIds, []);
    assert.equal(userOnly.completedPending, false);
    assert.equal(userOnly.historyRev, 5);
  });
});
