# Graph Report - computer-use-agent  (2026-09-02)

## Corpus Check
- 210 files · ~190,185 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3218 nodes · 7198 edges · 167 communities (137 shown, 29 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 191 edges (avg confidence: 0.89)
- Token cost: 26,078 input · 7,160 output

## Community Hubs (Navigation)
- App Status
- Face Overlay
- App
- Memory
- Tts Kokoro
- Stt Whisperflow
- Input Queues
- Phone Gateway
- Log Overlay
- Wake
- Tests Phone Gateway
- Stt Init
- Skills
- Chat Overlay
- Audio
- Agent
- App Status
- Orchestrator
- Cua
- Tests Orchestrator Questions
- Chat Store
- Session Compact
- Displays
- Tts Low Latency
- Tests Memory
- Chat Bridge
- Tests Observe
- Browser Data
- Tts Init
- Speaker Id
- Session
- Orchestrator
- Orchestrator
- Llm Client
- Chat Bridge
- Tools Registry
- Tests Skills
- Context
- Stt Init
- Tests Mark Done
- Dictation Overlay
- Evaluator
- Speaker Enroll
- Observe
- Tests Browser Data
- Tests Speaker Id
- Tests Actions
- Tests Wake
- Latency Report
- Tests Orchestrator Task Guard
- Observe
- Recipes
- Tests Cua
- Webmcp
- Dictation
- Stt Init
- Mcp Auth
- Mcp Auth
- Recipes
- Tests Mcp
- Accessibility
- Actions
- Barge Router
- Mcp Client
- Task Feedback
- Tests Recipes
- Tests Tts Voice
- Mcp Client
- Tests Task Spec
- Speaker Id
- Tests Displays
- Actions
- Chat App Main
- Recipes
- Artifact Paths
- Dictation
- Recipes
- Tests Low Latency Tts
- Tests Mcp Auth
- Execution Router
- Observe
- Tests Chat Bridge Face
- Speaker Output
- Wake
- Tests Whoami
- Timers
- Wake
- Tts Init
- Keyboard Barge
- Tests Context
- Tests Dictation
- Tests Observe
- Tests Session Compact
- Tests Timers
- Chat App Package
- Readme
- Bus
- Stt Init
- Tests Llm Client
- Tests Webmcp
- Actions
- Observe
- Recipes
- Tts Sarvam
- Webmcp Chromium
- Tests Chat Stream
- Tests Phone Tts
- Tests Tools Registry
- Mcp Auth
- Dictation
- Stt Init
- Task Log
- Echo Mcp Server
- Envfile
- Terminal
- Tests Chat Bridge Displays
- Tests Chat Screenshot Turn
- Tests Dictation Overlay
- Tests Recipes
- Tests Recipes
- Tests Stt Phone
- Demo1
- Core 122
- Stt Init
- Tests Recipes
- Tests Recipes
- Tests Chat Bridge Speakers
- Mcp Auth
- Core 128
- Tts Openai
- Wake
- Demo1 Poster
- Core 132
- Core 133
- Core 134
- Core 135
- Core 136
- Core 137
- Core 138
- Core 139
- Tests Chat Bridge Mcp
- Tests Observe
- Wake
- Demo1 Poster
- Core 144
- Core 145
- Core 146
- Core 147
- Core 148
- Core 149
- Core 150
- Core 151
- Chat App Preload
- Cua
- Core 154
- Core 155
- Core 156
- Core 157
- Core 158
- Core 159
- Core 160
- Core 161
- Agents
- Core 163
- Core 164
- Core 165

## God Nodes (most connected - your core abstractions)
1. `_read()` - 69 edges
2. `run_orchestrator()` - 62 edges
3. `_write()` - 56 edges
4. `read_status()` - 54 edges
5. `run()` - 49 edges
6. `TaskLog` - 44 edges
7. `LowLatencyTTS` - 33 edges
8. `_supervise_agent()` - 32 edges
9. `main()` - 30 edges
10. `wire()` - 29 edges

## Surprising Connections (you probably didn't know these)
- `_handle_read_skill()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `run()` --uses--> `RecipeHit`  [INFERRED]
  agent.py → recipes.py
- `AudioSession` --uses--> `Session`  [INFERRED]
  audio.py → session.py
- `AudioSessionTests` --uses--> `AudioSession`  [INFERRED]
  tests/test_audio.py → audio.py
- `run_webmcp_tool()` --uses--> `BrowserDataError`  [INFERRED]
  webmcp.py → browser_data.py

## Import Cycles
- None detected.

## Communities (167 total, 29 thin omitted)

### Community 0 - "App Status"
Cohesion: 0.05
Nodes (86): begin_tts_playback(), chat_stream_payload(), clear_cancel(), clear_logs(), clear_mark_done(), clear_phone_photo(), clear_quit_request(), clear_send() (+78 more)

### Community 1 - "Face Overlay"
Cohesion: 0.05
Nodes (51): blob_outline_points(), blobatar_ids(), blobatar_png_bytes(), BlobatarSpec, chat_avatar_pngs(), cmd_face(), current_blobatar(), _extras_circle() (+43 more)

### Community 2 - "App"
Cohesion: 0.06
Nodes (83): acceptDrafts(), applyCustomFace(), applyDisplaysPayload(), applyFaceStatus(), applyObserveStatus(), autosize(), boot(), bufferToBase64() (+75 more)

### Community 3 - "Memory"
Cohesion: 0.08
Nodes (68): Replace a memory file's markdown contents (full-file edit)., write_memory_payload(), apply_condensed_memory_files(), apply_extracted_memory_items(), _canonical_kind(), capture_and_save_screen(), _capture_png(), capture_screen_png() (+60 more)

### Community 4 - "Tts Kokoro"
Cohesion: 0.06
Nodes (56): KokoroSynthesizeTests, PiperSynthesizeTests, PiperVoicePathTests, Local Piper / Kokoro TTS adapters., _read_wav_frames(), _audio_from_result(), _ensure_misaki_en(), _ensure_mlx_g2p_fallback() (+48 more)

### Community 5 - "Stt Whisperflow"
Cohesion: 0.06
Nodes (47): _load_wav(), _log(), main(), _openai_model(), _provider_ready(), Path, race_once(), RaceResult (+39 more)

### Community 6 - "Input Queues"
Cohesion: 0.05
Nodes (38): AgentMessageInbox, AgentMessagePublisher, extract_jarvis_command(), ZeroMQ message bus: orchestrator → computer agent (while agent is running).…, Drain typed messages into steer / follow_up / next_run buckets., Return the command after a leading wake phrase, or None if absent. Kept for…, Orchestrator side: enqueue user directives for a running agent., Agent side: non-blocking drain of queued orchestrator messages. (+30 more)

### Community 7 - "Phone Gateway"
Cohesion: 0.07
Nodes (46): read_phone_screen(), read_phone_speech(), set_phone_gateway_pid(), advertise_urls(), audio_to_wav(), ensure_phone_gateway(), ingest_phone_audio(), ingest_phone_photo() (+38 more)

### Community 8 - "Log Overlay"
Cohesion: 0.07
Nodes (30): Ask the tray overlay to hide (True) or show (False) for a screenshot., set_overlay_hidden(), format_overlay_text(), LogOverlay, overlay_enabled(), overlay_frame_top_left(), overlay_owner_alive(), overlay_should_show() (+22 more)

### Community 9 - "Wake"
Cohesion: 0.07
Nodes (51): publish_phone_screen(), Share the latest computer-use screenshot with the phone gateway., _afplay(), _default_phrase_for_models(), _default_wake_model(), _download_file(), _ensure_model(), format_end_listen_phrases() (+43 more)

### Community 10 - "Tests Phone Gateway"
Cohesion: 0.05
Nodes (8): AdvertiseUrlsTests, EnsureGatewayTests, PhoneAudioIngestTests, PhoneGatewayEnabledTests, PhoneGatewayHttpTests, PhoneGatewayTokenTests, PhonePhotoIngestTests, Phone gateway: env switch, auth, command queue (no live network bind required).

### Community 11 - "Stt Init"
Cohesion: 0.09
Nodes (50): cancel_pending(), consume_cancel(), True if Cancel was requested; clears the flag so it fires once., _cancel_pending(), _cancel_requested(), _capture_sample_rate(), _cue_listen_start(), _emit_partial() (+42 more)

### Community 12 - "Skills"
Cohesion: 0.09
Nodes (48): _handle_read_skill(), cmd_condense_skills(), cmd_merge_skills(), _condense_one_skill(), condense_skills(), delete_skill_folder(), discover_skills(), format_skill_catalog() (+40 more)

### Community 13 - "Chat Overlay"
Cohesion: 0.07
Nodes (40): pid_alive(), Show or hide the desktop chat window (tray menu / cua chat)., set_chat_app_pid(), set_chat_bridge_pid(), set_chat_overlay_enabled(), ensure_chat_bridge(), Popen, Start the bridge subprocess if not already running. (+32 more)

### Community 14 - "Audio"
Cohesion: 0.08
Nodes (35): listen_pending(), Whether the current turn should speak replies (vs chat text only)., Tag the current orchestrator turn (chat / voice / phone / …)., set_reply_tts(), set_turn_source(), speak_pending(), utterance_pending(), AudioSession (+27 more)

### Community 15 - "Agent"
Cohesion: 0.10
Nodes (40): DesktopController, Wraps pyautogui with coordinate remapping between screenshot space and actual…, _action_summary(), confirm(), _confirm_terminal(), _extract_json_object(), _extract_memories_from_log(), _handle_ask_user() (+32 more)

### Community 16 - "App Status"
Cohesion: 0.08
Nodes (42): ack_overlay_hidden(), active_agents(), cmd_sleep(), format_tooltip(), Any, Soft-quit via flag, then SIGTERM the orchestrator process if known. Returns…, Plain-text tooltip for NSStatusItem hover., Snapshot for the tray (or callers). (+34 more)

### Community 17 - "Orchestrator"
Cohesion: 0.10
Nodes (43): chat_text_only(), log_llm(), Put an LLM reply in the status log (and ``last_llm``) for the phone / tray., Chat turn with speaker off — reply in the UI, not via TTS or status blurbs., reply_tts_enabled(), set_last_spoken(), get_audio(), current_trace_id() (+35 more)

### Community 18 - "Cua"
Cohesion: 0.10
Nodes (40): _cleanup_side_processes(), _clear_pid_file(), cmd_help(), cmd_install(), cmd_start(), cmd_status(), cmd_stop(), cua_on_path() (+32 more)

### Community 19 - "Tests Orchestrator Questions"
Cohesion: 0.07
Nodes (21): _assistant_message_text(), _confirm_heard_enabled(), _give_response_closes_turn(), _looks_like_question(), Build Responses API ``input`` for one user turn (optional phone + desktop…, Plain assistant text from a Responses API turn (not tool-call arguments)., True when spoken text expects a reply (so we must open the mic)., Drop trailing 'I'll wait / I'm ready' padding from a spoken reply. (+13 more)

### Community 20 - "Chat Store"
Cohesion: 0.09
Nodes (15): ChatRow, ChatStore, _connect(), _init_schema(), MessageRow, Path, Local SQLite chat history + screenshot files for the desktop chat UI., Thread-safe SQLite store for chats / messages / prefs. (+7 more)

### Community 21 - "Session Compact"
Cohesion: 0.09
Nodes (26): CheckpointResult, Any, Orchestrator turn checkpoint (harness-v2 §4). Between turns the lane passes a…, Run one orchestrator checkpoint before (or after recovering) a model call.…, run_orchestrator_checkpoint(), _clip(), compact_session_thread(), _extract_response_text() (+18 more)

### Community 22 - "Displays"
Cohesion: 0.13
Nodes (37): _as_mapping(), assign_windows_to_monitors(), _cg_window_list(), _clip_url(), format_browser_tabs(), format_monitor_occupancy(), format_running_apps(), _frontmost_name() (+29 more)

### Community 23 - "Tts Low Latency"
Cohesion: 0.10
Nodes (13): LowLatencyTTS, Thread-safe two-stage (synthesis → playback) streaming TTS pipeline., Reuse the process-wide persistent wake monitor (never stop it here)., Wake and/or keyboard interrupt event + release callback., Stop remaining synthesis/playback after a wake-word barge-in., Begin a streaming TTS session for ``response_id`` (public API)., Append plaintext to the active stream and queue speakable clauses., Finalize the active stream: flush remaining text into the synth queue. (+5 more)

### Community 24 - "Tests Memory"
Cohesion: 0.06
Nodes (5): CondenseMemoryTests, ExtractMemoryTests, MemoryStoreTests, Tests for personal / app memory storage., TurnTraceTests

### Community 25 - "Chat Bridge"
Cohesion: 0.13
Nodes (26): accept_observe_draft(), _capture_desktop_png(), _chat_row(), ChatBridgeHandler, command_for_orchestrator(), displays_payload(), _json_body(), list_mcp_connections() (+18 more)

### Community 26 - "Tests Observe"
Cohesion: 0.10
Nodes (8): Focus, SessionBuffer, ExcludeAppTests, FocusedDisplayCaptureTests, ObserverFlushTests, ParseExtractTests, Tests for the passive observer (session flush, drafts, accept)., SessionBufferTests

### Community 27 - "Browser Data"
Cohesion: 0.13
Nodes (25): _apply_operation(), BrowserDataError, _decode(), fetch_chromium(), fetch_lightpanda(), fetch_page(), _lightpanda_binary(), _lightpanda_json() (+17 more)

### Community 28 - "Tts Init"
Cohesion: 0.13
Nodes (30): reply_sink(), _apply_fade(), _numpy(), _phone_reply_sink(), _play_afplay(), _play_sounddevice(), play_wav(), OpenAI (+22 more)

### Community 29 - "Speaker Id"
Cohesion: 0.12
Nodes (27): _log_speaker_round(), Read voice ID for this round, update session state, log only (no tool use yet).…, _accept_match(), agent_speaker_context(), enabled(), get_last_speaker(), identify(), _identify_wav_bytes() (+19 more)

### Community 30 - "Session"
Cohesion: 0.10
Nodes (13): bind_session(), _canon(), Any, Explicit voice-session phases. Tray status is a projection of this machine.…, Illegal phase transition (strict mode only)., In-process session. ``enter`` writes the tray JSON via app_status., Move to ``phase``. Returns the phase actually entered., Install the process-wide session. Pass None to clear. (+5 more)

### Community 31 - "Orchestrator"
Cohesion: 0.11
Nodes (26): phone_photo_pending(), quit_requested(), is_save_screen_utterance(), True when the user wants the current display stored as memory., _announce_llm_failure(), _format_task_history(), _heard_confirm_line(), _history_note() (+18 more)

### Community 32 - "Orchestrator"
Cohesion: 0.12
Nodes (22): True when this turn was queued from the Electron chat app., reply_to_chat(), _create_response(), _exception_blob(), is_fatal_llm_error(), llm_error_speech(), LlmUnavailableError, _print_messages() (+14 more)

### Community 33 - "Llm Client"
Cohesion: 0.12
Nodes (28): _continue_response(), Follow-up Responses turn. DeepSeek must replay function_call items (stateless)., agent_provider(), fold_orphan_tool_outputs(), function_call_input_items(), input_has_image(), _item_call_id(), _item_output_text() (+20 more)

### Community 34 - "Chat Bridge"
Cohesion: 0.11
Nodes (26): Write a chat-attached PNG for the orchestrator; return basename for enqueue., save_chat_screenshot_png(), chat_bridge_enabled(), delete_mcp_connection(), ensure_inbox_worker(), _face_option(), face_status_payload(), load_or_create_token() (+18 more)

### Community 35 - "Tools Registry"
Cohesion: 0.14
Nodes (28): Brain, mcp_openai_tools(), agent_tools(), _entry(), execute_prepared_tool(), _execute_read_screen(), finalize_tool_outcome(), ImmediateToolOutcome (+20 more)

### Community 36 - "Tests Skills"
Cohesion: 0.14
Nodes (9): CondenseParseTests, CondenseRunTests, CuaSkillsCommandTests, DiscoverSkillsTests, MergeParseTests, MergeRunTests, Path, Tests for skill discovery and cua skills condense. (+1 more)

### Community 37 - "Context"
Cohesion: 0.12
Nodes (26): format_display_context(), list_monitors(), Return attached displays with logical geometry (top-left origin). On macOS uses…, Human-readable display summary for the model’s starting context., assemble_context(), _capture_desktop_context(), capture_turn_desktop_context(), _clip() (+18 more)

### Community 38 - "Stt Init"
Cohesion: 0.10
Nodes (25): ask_user(), _consume_phone_utterance(), _end_phrase_live_enabled(), _EndPhraseWatcher, listen_and_confirm(), _listen_end_hint(), _listen_end_spotter(), listen_once() (+17 more)

### Community 39 - "Tests Mark Done"
Cohesion: 0.07
Nodes (3): FlagTests, Tests for mark-done utterances and status flags., UtteranceTests

### Community 40 - "Dictation Overlay"
Cohesion: 0.11
Nodes (17): dictation_overlay_enabled(), DictationDotsOverlay, dot_alphas(), hide_dictation_overlay(), init_dictation_overlay(), overlay_frame_near_point(), Any, Cursor overlay for Fn dictation: dots while holding, spinner after release. (+9 more)

### Community 41 - "Evaluator"
Cohesion: 0.15
Nodes (24): AgentRoute, _client_for_model(), coach_agent(), _extract_json(), max_steps_for_difficulty(), model_for_recipe_handoff(), Any, OpenAI (+16 more)

### Community 42 - "Speaker Enroll"
Cohesion: 0.17
Nodes (23): enroll_speaker_from_body(), cmd_delete(), cmd_enroll(), cmd_list(), cmd_test(), main(), OpenAI, Interactive speaker enrollment: read five passages (three long, two short),… (+15 more)

### Community 43 - "Observe"
Cohesion: 0.18
Nodes (22): accept_draft(), _append_events_log(), _archive_draft(), cmd_accept(), cmd_list(), cmd_reject(), _find_drafts(), format_draft_listing() (+14 more)

### Community 44 - "Tests Browser Data"
Cohesion: 0.10
Nodes (6): BrowserDataTests, _Headers, _Opener, dict, Tests for safe structured webpage retrieval., _Response

### Community 45 - "Tests Speaker Id"
Cohesion: 0.13
Nodes (8): AgentSpeakerContextTests, _alice_samples(), _mock_embed(), ndarray, Speaker ID unit tests (no microphone)., Deterministic fake embeddings: low freqs = speaker A, high = speaker B., _sine_wav(), SpeakerIdTests

### Community 46 - "Tests Actions"
Cohesion: 0.08
Nodes (8): BrowserOverlayDismissTests, KeypressBlockTests, MultiDisplayTests, Tests for desktop action helpers (typing, modifiers)., ReleaseModifiersTests, ScreenshotPublishTests, TypeModeTests, TypeTextTests

### Community 47 - "Tests Wake"
Cohesion: 0.08
Nodes (7): AfplayChimeTests, EndModelKeyTests, OverAndOutChimeTests, Wake-phrase stripping and listen-end spotting (no ONNX required)., StripTrailingTests, WakeIdentityTests, WakeSpotterTests

### Community 48 - "Latency Report"
Cohesion: 0.19
Nodes (21): _append_trace(), build_report(), _durations(), finish_trace(), _fmt_ms(), _percentile(), Any, Path (+13 more)

### Community 49 - "Tests Orchestrator Task Guard"
Cohesion: 0.14
Nodes (18): User utterance plus each LLM step (replies, tool calls, results)., TurnTrace, _completed_task_match(), _completed_tasks_in_turn(), _normalized_task_goal(), Stable form for rejecting accidental post-completion relaunches., Return a completed near-duplicate from this orchestrator session., Pair start_task/result trace steps from only the current user turn. (+10 more)

### Community 50 - "Observe"
Cohesion: 0.15
Nodes (22): _capture_cg_display(), _capture_focused_display(), _capture_png(), _capture_png_bytes(), _capture_primary_png(), cmd_start(), cmd_status(), cmd_stop() (+14 more)

### Community 51 - "Recipes"
Cohesion: 0.19
Nodes (21): _extract_json_object(), fill_recipe_slots(), fill_recipe_slots_llm(), find_matching_recipe(), format_recipe_catalog(), load_recipes(), maybe_save_recipe(), _maybe_save_recipe_impl() (+13 more)

### Community 52 - "Tests Cua"
Cohesion: 0.09
Nodes (5): MainTests, Tests for the cua daemon CLI helpers., RunningPidTests, ShimTests, StartStopTests

### Community 53 - "Webmcp"
Cohesion: 0.21
Nodes (17): _chromium_binary(), _bridge(), _BridgeSession, call_webmcp_tool(), list_webmcp_tools(), _node_binary(), _persistent_bridge(), Any (+9 more)

### Community 54 - "Dictation"
Cohesion: 0.16
Nodes (20): cmd_start(), cmd_status(), cmd_stop(), dictation_enabled(), ensure_dictation_running(), _install_fn_tap(), _is_globe_fn_key(), _keystroke_v() (+12 more)

### Community 55 - "Stt Init"
Cohesion: 0.10
Nodes (20): _dictation_provider(), listen_dictation(), Path, Write captured mic audio (and optional transcript) under recordings/., One-shot file transcription (OpenAI, Sarvam Saaras, or local WhisperFlow)., Hold-to-talk dictation with live partials; ends on Fn release (Send), not…, Providers that record a clip, then run file STT (no live partials)., Which STT backend Fn dictation uses. (+12 more)

### Community 56 - "Mcp Auth"
Cohesion: 0.21
Nodes (20): build_oauth_provider(), cmd_mcp_login(), cmd_mcp_logout(), format_apps_help(), _gh_bin(), _gh_login_browser(), _gh_token(), is_dcr_failure() (+12 more)

### Community 57 - "Mcp Auth"
Cohesion: 0.17
Nodes (8): FileTokenStorage, format_status(), logged_in_names(), oauth_httpx_auth(), Any, Path, httpx Auth for a connected HTTP MCP server, or None., JSON token + client-info store (chmod 600).

### Community 58 - "Recipes"
Cohesion: 0.20
Nodes (19): _bind_without_template(), collect_logged_commands(), _computer_action_count(), _default_templates(), parameterize_opened_url(), propose_recipe_from_log(), Parameterized desktop recipes: stable prefix, optional computer-use handoff. A…, Poll until the target app is frontmost, instead of a fixed sleep. (+11 more)

### Community 59 - "Tests Mcp"
Cohesion: 0.10
Nodes (6): skipUnless, ConfigTests, ConnectErrorIsolationTests, LiveStdioTests, Tests for MCP config, read-only gating, and a live stdio echo server., ReadOnlyTests

### Community 60 - "Accessibility"
Cohesion: 0.21
Nodes (19): accessibility_available(), _ax_frame(), _ax_get(), _ax_str(), _collect_lines(), _find_app(), focused_edit_info(), _frontmost_app() (+11 more)

### Community 61 - "Actions"
Cohesion: 0.15
Nodes (18): capture_all_displays_enabled(), _capture_cg_display(), capture_displays_png(), capture_monitor_image(), desktop_logical_bounds(), desktop_logical_size(), _ns_display_id(), Translates OpenAI computer-use actions into real mouse/keyboard input via… (+10 more)

### Community 62 - "Barge Router"
Cohesion: 0.12
Nodes (12): BargeDecision, classify_barge_utterance(), _extract_json(), Any, OpenAI, Classify TTS barge-in: new computer task vs answer/clarification., Result of LLM barge-in routing., Ask a cheap model whether a barge-in replaces the current work with a new task.… (+4 more)

### Community 63 - "Mcp Client"
Cohesion: 0.20
Nodes (14): expand_env_value(), _expand_map(), _format_call_result(), load_mcp_config(), McpTool, parse_mcp_arguments(), _parse_servers(), Any (+6 more)

### Community 64 - "Task Feedback"
Cohesion: 0.17
Nodes (18): collect_post_task_feedback(), feedback_enabled(), interpret_feedback_text(), load_task_actions(), Any, OpenAI, Post-task user feedback: spoken prompt, persisted with goal and action log., Ask the user whether the task worked; persist with goal and actions. (+10 more)

### Community 65 - "Tests Recipes"
Cohesion: 0.16
Nodes (5): TestCase, GroundingTests, Path, RecipeRunTests, _seed_dir()

### Community 66 - "Tests Tts Voice"
Cohesion: 0.19
Nodes (12): LocalVoiceMappingTests, dict, patch, ActiveTtsVoiceTests, patch, Wake-word → Sarvam TTS speaker mapping., SpeakLaterTests, active_tts_voice() (+4 more)

### Community 67 - "Mcp Client"
Cohesion: 0.22
Nodes (10): get_manager(), _is_fatal(), _LiveServer, _mcp_error_text(), McpManager, BaseException, Long-lived MCP sessions on a background asyncio loop., Connect (or reconnect) a configured server. Returns an error string or None. (+2 more)

### Community 68 - "Tests Task Spec"
Cohesion: 0.16
Nodes (11): _looks_like_agent_brief(), AgentTaskSpec, is_procedure_brief(), Planner vs actor: start_task is a goal, not a UI screenplay. The orchestrator…, True when the text is a how-to screenplay instead of a user goal., What the actor should match on vs what it should optimize for., Recipes match ``match_text`` (the spoken request). The computer-use prompt uses…, resolve_agent_task() (+3 more)

### Community 69 - "Speaker Id"
Cohesion: 0.18
Nodes (19): _audio_at_embed_rate(), _best_similarity(), cosine_similarity(), embed_wav_bytes(), enroll_speaker(), _get_embedder(), load_profile(), _pairwise_min() (+11 more)

### Community 70 - "Tests Displays"
Cohesion: 0.13
Nodes (7): _cg_window(), LiveLayoutMemorySkipTests, _monitor(), OccupancyFormatTests, Per-monitor window occupancy without requiring Quartz., RunningAppsAndTabsTests, WindowGeometryTests

### Community 71 - "Actions"
Cohesion: 0.12
Nodes (15): ActionStopped, _dismiss_suggestion_overlay(), _is_blocked_chord(), _mac_scroll_pixels(), normalize_key(), Exception, Post trackpad-like continuous pixel scroll events via Quartz. pyautogui's line-…, Scroll by approximate pixel deltas. dy>0 scrolls content up (wheel up). (+7 more)

### Community 72 - "Chat App Main"
Cohesion: 0.19
Nodes (16): { app, BrowserWindow, ipcMain, shell, session, systemPreferences }, applyOverlayBehavior(), BRIDGE_PORT, bridgeRequest(), CONTROL_PORT, createWindow(), fs, hideMainWindow() (+8 more)

### Community 73 - "Recipes"
Cohesion: 0.16
Nodes (17): _bind_recipe(), extract_maps_place(), extract_media_query(), _has_map_word(), match_template(), _prelude_is_maps(), _prelude_is_youtube(), _prelude_is_youtube_music() (+9 more)

### Community 74 - "Artifact Paths"
Cohesion: 0.25
Nodes (14): default_output_dir(), ensure_output_dir(), output_rule(), Path, Canonical paths for user-facing files created by the computer-use agent., Default destination unless the user explicitly names another location., format_not_to_do(), Always-on don'ts for the agent and orchestrator. (+6 more)

### Community 75 - "Dictation"
Cohesion: 0.22
Nodes (5): _backspace_n(), LiveDictationPaster, Paste growing STT partials; revise via AX or backspace when text changes., Sync to the final transcript and restore the clipboard., Remove anything we inserted (cancel) and restore the clipboard.

### Community 76 - "Recipes"
Cohesion: 0.19
Nodes (15): apply_params(), _normalize_http_url(), open_app(), open_url(), placeholders_in(), Exception, Prelude failed; caller should fall through to computer-use., Prefix https:// for bare hosts (draw.io → https://draw.io). (+7 more)

### Community 77 - "Tests Low Latency Tts"
Cohesion: 0.22
Nodes (9): DecodedMessagePrefixTests, _engine(), PublicApiTests, patch, Unit tests for low-latency streaming TTS public API and helpers., decoded_message_prefix(), extract_message_field(), Best-effort final ``message`` from complete or nearly-complete tool JSON. (+1 more)

### Community 78 - "Tests Mcp Auth"
Cohesion: 0.13
Nodes (4): ConfigUpsertTests, Tests for MCP browser-login helpers (no live OAuth)., ResolveAppTests, TokenStorageTests

### Community 79 - "Execution Router"
Cohesion: 0.24
Nodes (11): ExecutionRoute, _matching_recipe_name(), Deterministic fast/slow routing and specialist execution lanes. The router…, Choose a cheap first approach and the specialist prompt lane., resolve_execution_route(), test_browser_submission_uses_slow_path(), test_dense_cad_routes_to_visual_slow_path(), test_git_routes_to_terminal_fast_path() (+3 more)

### Community 80 - "Observe"
Cohesion: 0.30
Nodes (4): computer_use_active(), exclude_app(), Observer, True while a computer-use job owns the pointer.

### Community 81 - "Tests Chat Bridge Face"
Cohesion: 0.18
Nodes (4): SimpleNamespace, FacePayloadTests, Chat bridge face overlay helpers., ChatTextOnlySpeakTests

### Community 82 - "Speaker Output"
Cohesion: 0.18
Nodes (9): _app_playing(), media_playing(), _osascript(), Whether media is playing on the Mac — for the computer-use agent. Reports only…, True when Music or Spotify reports player state ``playing``., One-line status for the agent, or empty when disabled., speaker_output_block(), Media playing yes/no for the agent (no AppleScript in tests). (+1 more)

### Community 83 - "Wake"
Cohesion: 0.16
Nodes (14): _strip_listen_wake(), matches_wake_phrase(), normalize_speech_text(), _parse_wake_phrases(), _phrases_to_check(), Comma-separated wake phrases; longest-first friendly, case-preserving., True if transcript starts with (or equals) any configured wake phrase., Remove a leading wake phrase from a transcript (tries longest match first). (+6 more)

### Community 84 - "Tests Whoami"
Cohesion: 0.18
Nodes (8): who_am_i reads README.md for self-description., WhoAmITests, format_whoami_output(), Path, who_am_i tool: load this project's README so the agent can describe itself., Return README markdown with HTML stripped (demo embeds, etc.)., read_project_readme(), run_whoami_tool()

### Community 85 - "Timers"
Cohesion: 0.25
Nodes (13): cancel_timer(), _fire(), list_timers(), _next_id(), notify_macos(), _osa_str(), Any, In-process timers: schedule, list, cancel. No Clock.app, no model-exec. A… (+5 more)

### Community 86 - "Wake"
Cohesion: 0.14
Nodes (6): Background wake-word listener for barge-in / idle wait. By default runs until…, Release the mic so STT (or another capture) can use it., Resume wake listening after STT (clears a stale woken flag)., Acknowledge a wake so listening can continue (persistent mode)., Block until woken (or should_stop / timeout). Assumes this monitor is already…, WakeMonitor

### Community 87 - "Tts Init"
Cohesion: 0.15
Nodes (10): Any, concat_wavs(), Join WAV blobs that share the same format (streaming TTS chunks)., Print a ``[tts-latency] …`` line when TTS_LATENCY_LOG=1., tts_latency_print(), OpenAI, Path, Non-blocking, chunked TTS pipeline used by the voice orchestrator. Public API… (+2 more)

### Community 88 - "Keyboard Barge"
Cohesion: 0.29
Nodes (11): acquire_tts_interrupt(), _drain_stdin(), _ensure_listener_locked(), _enter_cbreak(), keyboard_barge_enabled(), _listener_loop(), Keyboard barge-in during TTS (terminal key → stop speech → listen). When the…, Return ``(event, release)`` set when any source or a barge key fires. Always… (+3 more)

### Community 89 - "Tests Context"
Cohesion: 0.15
Nodes (4): ContextBundleTests, NotToDoTests, Ephemeral context bundle (not durable memory)., TurnDesktopContextTests

### Community 92 - "Tests Session Compact"
Cohesion: 0.15
Nodes (5): CheckpointTests, FoldTaskHistoryTests, FormatTaskHistoryTests, OverflowTests, Session compaction for orchestrator context limits.

### Community 94 - "Chat App Package"
Cohesion: 0.17
Nodes (11): dependencies, electron, description, main, name, private, scripts, dev (+3 more)

### Community 95 - "Readme"
Cohesion: 0.17
Nodes (12): Durable memory store, Always-on computer-use policy, Isolated virtual desktop layer, HTTP-to-visible-browser escalation, Fast-path and slow-path execution router, MCP integrations, Personal Computer Use Agent, Computer-use safety and privacy controls (+4 more)

### Community 96 - "Bus"
Cohesion: 0.18
Nodes (6): AskUserBridge, Blocking ask_user from the agent worker thread to the orchestrator main thread.…, Called from the agent worker thread. Blocks until orchestrator replies., True if the agent has queued an ask_user the orchestrator hasn't taken yet., Called from the orchestrator. Returns {id, question} or None., Called from the orchestrator after speaking/listening.

### Community 97 - "Stt Init"
Cohesion: 0.31
Nodes (5): FanNoiseFilter, _float_to_pcm16_b64(), _peak(), ndarray, High-pass + adaptive spectral gate tuned for steady laptop/room fan noise.

### Community 99 - "Tests Webmcp"
Cohesion: 0.25
Nodes (3): discovery(), WebMCP discovery, validation, and mutation-boundary tests., WebMCPTests

### Community 100 - "Actions"
Cohesion: 0.22
Nodes (10): _mac_type_paste(), _mac_type_unicode(), Type via Unicode events — avoids virtual-key shortcuts (dictation, emoji…, Paste via clipboard — fallback when Unicode injection fails in a field., Inject text into the focused control., How to inject text for computer-use ``type`` actions., Release common modifiers so the next keys go to the focused field, not…, release_stuck_modifiers() (+2 more)

### Community 101 - "Observe"
Cohesion: 0.24
Nodes (3): Accumulates closed sessions until OBSERVE_DRAFT_SECONDS have elapsed., WindowBuffer, WindowBufferTests

### Community 102 - "Recipes"
Cohesion: 0.22
Nodes (10): handoff_prompt(), leftover_is_screenshot_only(), leftover_text(), Short remainder after a URL open — never 'create a new tab / navigate'., True when leftover is capture-the-window, not zoom/play/click., Run a matching recipe prelude. Returns a status string when the recipe finished…, RecipeHit, save_recipe_screenshot() (+2 more)

### Community 103 - "Tts Sarvam"
Cohesion: 0.29
Nodes (9): get_client(), Shared SarvamAI client (STT + TTS)., Print a ``[tts] …`` line when TTS_LOG=1 (or ``force`` for real errors)., tts_print(), _pcm_to_wav(), Sarvam AI Bulbul text-to-speech (HTTP streaming → WAV)., Stream speech via Sarvam ``convert_stream`` (linear16) and return a WAV. Uses…, _split_text() (+1 more)

### Community 104 - "Webmcp Chromium"
Cohesion: 0.29
Nodes (7): command(), deadlineMs, execute(), pending, run(), start(), startup

### Community 106 - "Tests Phone Tts"
Cohesion: 0.31
Nodes (3): PhoneTtsSinkTests, Phone reply sink: synthesize on Mac, skip afplay, publish WAV., _silence_wav()

### Community 108 - "Mcp Auth"
Cohesion: 0.25
Nodes (3): AbstractEventLoop, CallbackServer, Local HTTP listener for the OAuth redirect.

### Community 109 - "Dictation"
Cohesion: 0.25
Nodes (4): DictationDaemon, Switch dots ↔ spinner without hiding. No-op if the overlay is down., set_dictation_overlay_style(), Handle Fn alone edge. Returns True if the event should be swallowed.

### Community 110 - "Stt Init"
Cohesion: 0.25
Nodes (8): choose_transcript(), classify_yes_no(), _normalize_reply(), Pick the more relevant / coherent of live vs refined transcripts., Re-transcribe the committed clip with REFINE_MODEL and choose vs live. Returns…, Return 'yes', 'no', 'quit', 'retry', or None if unclear., refine_after_pause(), _response_output_text()

### Community 111 - "Task Log"
Cohesion: 0.32
Nodes (3): _jsonable(), Any, Path

### Community 112 - "Echo Mcp Server"
Cohesion: 0.32
Nodes (7): add(), delete_item(), echo(), Minimal stdio MCP server used by tests/test_mcp.py., Return the same text., Delete an item by id (write)., tool

### Community 113 - "Envfile"
Cohesion: 0.33
Nodes (6): configure_native_threads(), load_dotenv(), Path, Load a local .env into os.environ (no external dependency)., Cap BLAS/OpenMP threads before numpy/OpenBLAS loads. Unbounded OpenBLAS…, Parse KEY=VALUE lines from `.env` into the process environment. By default does…

### Community 114 - "Terminal"
Cohesion: 0.43
Nodes (6): _decode(), _format_report(), Run local shell commands for the computer-use agent. Captures stdout/stderr…, Execute `command` via the user's shell and return a text report. Uses the shell…, run_command(), _truncate()

### Community 118 - "Tests Recipes"
Cohesion: 0.43
Nodes (3): _FakeResponsesClient, LlmFillTests, Parameterized recipes: match templates, bind slots, skip unsafe URLs.

### Community 120 - "Tests Stt Phone"
Cohesion: 0.29
Nodes (3): AskUserTests, ListenOncePhoneTests, Phone-queued text must be accepted while STT is listening (ask_user).

### Community 121 - "Demo1"
Cohesion: 0.33
Nodes (6): Play Highway to Hell, Jarvis, Netflix Continue Watching, netflix-resume-continue-watching, Most-recent media resumption, resume-paused-media-across-apps

### Community 122 - "Core 122"
Cohesion: 0.33
Nodes (6): Metadata-preserving category move, move-downloads-categories-to-desktop, Safe extension-based Desktop organization, organize-desktop-by-extension, Safe extension-based Downloads organization, organize-downloads-by-extension

### Community 123 - "Stt Init"
Cohesion: 0.33
Nodes (3): _ListenHotkeys, TTY hotkeys while STT owns the mic: cancel (Esc) and optional send (Enter)., _stdin_is_tty()

### Community 126 - "Tests Chat Bridge Speakers"
Cohesion: 0.50
Nodes (3): list_speaker_payload(), Speaker list payload for the Electron manage-speakers page., SpeakerPayloadTests

### Community 128 - "Core 128"
Cohesion: 0.60
Nodes (5): Email snapshot schema, gmail-extract-latest-10-emails, gmail-extract-todays-emails, Email importance heuristics, gmail-flag-today-important-and-screenshot

### Community 129 - "Tts Openai"
Cohesion: 0.50
Nodes (4): OpenAI, OpenAI text-to-speech (gpt-4o-mini-tts, with tts-1-hd fallback)., Return WAV bytes from OpenAI speech synthesis., synthesize_wav()

### Community 130 - "Wake"
Cohesion: 0.50
Nodes (4): ndarray, Return True once when a wake phrase is detected on this stream., _resample_to_wake(), _score_from_predict()

### Community 131 - "Demo1 Poster"
Cohesion: 0.50
Nodes (4): Electronic Basics #1: The Multimeter by GreatScott!, Agent confirms video playback and audible audio, VS Code screenshot demonstrating the computer-use-agent project, YouTube search, selection, and tutorial playback skill

### Community 132 - "Core 132"
Cohesion: 0.50
Nodes (4): Job match scoring, find-jobs-matching-profile, LinkedIn post analytics, linkedin-capture-latest-post-analytics

### Community 133 - "Core 133"
Cohesion: 0.83
Nodes (4): Bluetooth Low Energy GATT, ESP32, iDotMatrix protocol, idotmatrix-ble-detection

### Community 134 - "Core 134"
Cohesion: 0.50
Nodes (4): open-app, Spotlight application launch, MCP-first web search, web-search

### Community 135 - "Core 135"
Cohesion: 0.50
Nodes (4): Preview Actual Size viewing, preview-open-and-zoom-image, Hardware pin identification, read-diagram-on-display-and-report-pins

### Community 136 - "Core 136"
Cohesion: 0.50
Nodes (4): Login-item and audio-agent cleanup, remove-third-party-keypress-sound, Process audio isolation, stop-terminal-audio-process

### Community 137 - "Core 137"
Cohesion: 0.50
Nodes (4): Content-derived image naming, rename-images-by-content, Representative-frame video classification, rename-videos-by-content

### Community 138 - "Core 138"
Cohesion: 0.50
Nodes (4): start-whatsapp-video-call-desktop, WhatsApp Desktop video call, whatsapp-call-contact, WhatsApp Desktop contact call

### Community 139 - "Core 139"
Cohesion: 0.50
Nodes (4): Pre-submission review gate, web-form-fill-attach-resume-and-pause, web-form-submit-capture-confirmation, Submission confirmation evidence

### Community 142 - "Wake"
Cohesion: 0.50
Nodes (4): _default_end_model_spec(), _parse_end_model_specs(), Prefer the bundled over-and-out ONNX when present., ONNX for ending a listen. Default: over_and_out.onnx if that file exists.

### Community 143 - "Demo1 Poster"
Cohesion: 0.67
Nodes (3): Mitigate false wake triggers by avoiding the wake phrase in spoken text and disabling barge-in on phrase matches, Text-to-speech output from speakers re-triggers the microphone wake detector, Wake phrase configuration through WAKE_PHRASE environment variable

### Community 144 - "Core 144"
Cohesion: 0.67
Nodes (3): diagramsnet-create-and-export-diagram, diagramsnet-create-pcb-pinout-from-image, diagramsnet-edit-and-export-drawio

### Community 145 - "Core 145"
Cohesion: 0.67
Nodes (3): Timestamped safety branch, git-merge-branch-into-main-with-backup, github-delete-branch-via-ui

### Community 146 - "Core 146"
Cohesion: 0.67
Nodes (3): Issue creation confirmation gate, github-create-issues-from-plan-md, github-find-own-repo-and-star-count

### Community 147 - "Core 147"
Cohesion: 0.67
Nodes (3): google-maps-get-directions, google-maps-open-place, google-maps-show-national-parks-country

### Community 148 - "Core 148"
Cohesion: 0.67
Nodes (3): MCP hardware control, Read-before-write device control, hardware-control-via-mcp

### Community 149 - "Core 149"
Cohesion: 0.67
Nodes (3): hn-comments, hn-edit-submission, hn-submit-repo

### Community 150 - "Core 150"
Cohesion: 0.67
Nodes (3): Gross Value Added at basic prices, Ministry of Statistics and Programme Implementation, india-quarterly-gdp-by-sector-piechart

### Community 151 - "Core 151"
Cohesion: 0.67
Nodes (3): manga-chapter-spoiler-verify-and-summarize, Independent-source spoiler cross-checking, medium-trending-extract-top-articles

## Knowledge Gaps
- **66 isolated node(s):** `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path`, `http`, `BRIDGE_PORT` (+61 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1129 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_status()` connect `App Status` to `App Status`, `Face Overlay`, `Chat Bridge`, `Phone Gateway`, `Log Overlay`, `Wake`, `Chat Overlay`, `Dictation`, `Observe`, `Cua`, `Observe`, `Dictation`, `Chat Bridge`, `Orchestrator`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `LowLatencyTTS` connect `Tts Low Latency` to `Orchestrator`, `Tests Low Latency Tts`, `Tts Init`, `Orchestrator`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `load_dotenv()` connect `Envfile` to `Chat Bridge`, `Tts Kokoro`, `Stt Whisperflow`, `Skills`, `Agent`, `App Status`, `Cua`, `Observe`, `Dictation`, `Orchestrator`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **What connects `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path` to the rest of the system?**
  _66 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App Status` be split into smaller, more focused modules?**
  _Cohesion score 0.051201671891327065 - nodes in this community are weakly interconnected._
- **Should `Face Overlay` be split into smaller, more focused modules?**
  _Cohesion score 0.050156739811912224 - nodes in this community are weakly interconnected._
- **Should `App` be split into smaller, more focused modules?**
  _Cohesion score 0.06368330464716007 - nodes in this community are weakly interconnected._