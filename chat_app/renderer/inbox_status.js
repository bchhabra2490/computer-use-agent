/* Shared inbox-status cursor for the chat UI (browser + Node tests). */

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.cuaInboxStatus = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function strIds(value) {
    return Array.isArray(value) ? value.map(String) : [];
  }

  function applyInboxStatus(prev, st) {
    const prevRev = Number(prev.historyRev || 0);
    const rev = Number(st.history_rev || 0);
    const chatRevs =
      st.chat_revs && typeof st.chat_revs === "object" ? st.chat_revs : {};
    const prevChatRevs = prev.chatRevs || {};
    const bridgeId = st.bridge_id ? String(st.bridge_id) : "";
    const prevBridgeId = prev.bridgeId ? String(prev.bridgeId) : "";
    const instanceChanged = !!(prevBridgeId && bridgeId && bridgeId !== prevBridgeId);
    const revWentBackwards = rev < prevRev;
    const resync = instanceChanged || revWentBackwards;

    let changedChatIds;
    if ("changed_chat_ids" in st && Array.isArray(st.changed_chat_ids)) {
      changedChatIds = strIds(st.changed_chat_ids);
    } else {
      changedChatIds = Object.keys(chatRevs)
        .filter((id) => Number(chatRevs[id] || 0) > Number(prevChatRevs[id] || 0))
        .map(String);
    }

    // Completions come from this payload. Read them before advancing historyRev
    // so a resync cannot skip a reply that later polls will never see again.
    let completedChatIds;
    if ("completed_chat_ids" in st && Array.isArray(st.completed_chat_ids)) {
      completedChatIds = strIds(st.completed_chat_ids);
    } else {
      completedChatIds = strIds(st.appended_chat_ids);
    }

    if (resync) {
      const forced = [prev.chatId, prev.pendingChatId].filter(Boolean).map(String);
      changedChatIds = [...new Set([...changedChatIds, ...forced])];
    }
    if (!completedChatIds.length && Number(st.assistant_appended || 0) > 0) {
      completedChatIds = changedChatIds.slice();
    }

    const revBumped = resync || rev > prevRev;
    return {
      resync,
      revBumped,
      historyRev: revBumped ? rev : prevRev,
      chatRevs,
      bridgeId: bridgeId || prevBridgeId,
      changedChatIds,
      completedChatIds,
      completedPending: completedChatIds.includes(String(prev.pendingChatId || "")),
    };
  }

  return { applyInboxStatus };
});
