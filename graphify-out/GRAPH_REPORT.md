# Graph Report - computer-use-agent  (2026-09-02)

## Corpus Check
- 210 files · ~194,348 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3270 nodes · 7238 edges · 186 communities (143 shown, 42 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 191 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2d55a58c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- app_status.py
- face_overlay.py
- app.js
- memory.py
- piper.py
- whisperflow.py
- emit
- phone_gateway.py
- log_overlay.py
- wake.py
- PhoneGatewayHttpTests
- _listen_realtime_body
- skills.py
- read_status
- chat_bridge.py
- agent.py
- kokoro.py
- orchestrator.py
- cua.py
- _process_response
- ChatStore
- checkpoint.py
- displays.py
- LowLatencyTTS
- MemoryStoreTests
- .do_POST
- Focus
- browser_data.py
- tts/__init__.py
- tts_race.py
- Session
- _user_turn_input
- _create_response
- llm_client.py
- pid_alive
- tools_registry.py
- Path
- context.py
- listen_once
- FlagTests
- dictation_overlay.py
- evaluator.py
- speaker_id.py
- Any
- BrowserDataTests
- SpeakerIdTests
- test_actions.py
- test_wake.py
- latency_report.py
- test_orchestrator_task_guard.py
- observe.py
- try_recipe
- MainTests
- test_tts_local.py
- dictation.py
- play_listen_end_chime
- mcp_auth.py
- FileTokenStorage
- utterance_match.py
- test_mcp.py
- accessibility.py
- actions.py
- barge_router.py
- mcp_client.py
- task_feedback.py
- _seed_dir
- active_tts_voice
- _mcp_error_text
- resolve_agent_task
- bus.py
- test_displays.py
- ._run_one
- main.js
- Recipe
- test_artifact_paths.py
- LiveDictationPaster
- recipes.py
- test_low_latency_tts.py
- ConfigUpsertTests
- resolve_execution_route
- Observer
- SimpleNamespace
- speaker_output.py
- strip_wake_phrase
- whoami.py
- log
- WakeMonitor
- .listen_command
- keyboard_barge.py
- test_context.py
- FnFlagTests
- DraftAcceptTests
- test_session_compact.py
- TimerToolTests
- package.json
- Personal Computer Use Agent
- AskUserBridge
- low_latency.py
- LlmClientTests
- type_text
- LogOverlay
- WindowBuffer
- fill_recipe_slots_llm
- tts_print
- webmcp_chromium.mjs
- ChatStreamTests
- PhoneTtsSinkTests
- ToolRegistryTests
- CallbackServer
- DictationDaemon
- stt/__init__.py
- TaskLog
- echo_mcp_server.py
- load_dotenv
- terminal.py
- McpManager
- ChatScreenshotTurnTests
- OverlayFrameTests
- main
- ._to_screen_coords
- test_stt_phone.py
- netflix-resume-continue-watching
- organize-downloads-by-extension
- list_speaker_payload
- listen_dictation
- TypeTextTests
- task_log.py
- BearerTokenAuth
- Email snapshot schema
- synthesize_wav
- _scroll
- Electronic Basics #1: The Multimeter by GreatScott!
- find-jobs-matching-profile
- Bluetooth Low Energy GATT
- open-app
- preview-open-and-zoom-image
- remove-third-party-keypress-sound
- rename-images-by-content
- start-whatsapp-video-call-desktop
- web-form-fill-attach-resume-and-pause
- test_chat_bridge_mcp.py
- ComputerUseGateTests
- Path
- Text-to-speech output from speakers re-triggers the microphone wake detector
- diagramsnet-create-and-export-diagram
- git-merge-branch-into-main-with-backup
- github-create-issues-from-plan-md
- google-maps-open-place
- hardware-control-via-mcp
- hn-submit-repo
- india-quarterly-gdp-by-sector-piechart
- manga-chapter-spoiler-verify-and-summarize
- preload.js
- cua script
- amazon-checkout-place-order
- GitHub contribution trend analysis
- morning-report MCP
- post-on-x-via-chrome
- Project memory store
- set-system-and-youtube-volume
- EasyEDA Pro
- Raspberry Pi Imager
- Graphify-first codebase workflow
- goodreads-export-read-shelf
- instagram-send-dm-by-name
- mac-clock-set-timer
- title_from_text
- LiveStdioTests
- convert-chart-figures-to-usd/SKILL.md
- cursor-generate-project-from-prompt/SKILL.md
- disable-terminal-bell-and-system-ui-sounds/SKILL.md
- _ns_display_id
- _text_looks_volatile_hardware
- check-mac-storage/SKILL.md
- chrome-copy-current-tab-url/SKILL.md
- chrome-move-tab-to-display-and-fullscreen/SKILL.md
- chrome-open-url-and-screenshot/SKILL.md
- chrome-play-youtube-music-playlist-by-name/SKILL.md
- chrome-play-youtube-music-track-by-name/SKILL.md
- contain-remove-terminal-dropper/SKILL.md
- delete-empty-desktop-folders/SKILL.md
- download-images-from-google-image-searches/SKILL.md
- inspect-suspicious-downloaded-installer/SKILL.md
- restore-ui-exit-or-kill-fullscreen-or-hung-process/SKILL.md
- rotate-and-clear-browser-sessions/SKILL.md

## God Nodes (most connected - your core abstractions)
1. `_read()` - 69 edges
2. `run_orchestrator()` - 62 edges
3. `_write()` - 56 edges
4. `read_status()` - 54 edges
5. `run()` - 49 edges
6. `TaskLog` - 45 edges
7. `LowLatencyTTS` - 33 edges
8. `_supervise_agent()` - 32 edges
9. `main()` - 30 edges
10. `wire()` - 29 edges

## Surprising Connections (you probably didn't know these)
- `_print_and_log_messages()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `_handle_ask_user()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `_handle_list_skills()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `_handle_read_skill()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `_handle_read_ui_text()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py

## Import Cycles
- None detected.

## Communities (186 total, 42 thin omitted)

### Community 0 - "app_status.py"
Cohesion: 0.05
Nodes (79): ack_overlay_hidden(), cancel_pending(), chat_stream_payload(), clear_cancel(), clear_logs(), clear_mark_done(), clear_phone_photo(), clear_quit_request() (+71 more)

### Community 1 - "face_overlay.py"
Cohesion: 0.05
Nodes (51): blob_outline_points(), blobatar_ids(), blobatar_png_bytes(), BlobatarSpec, chat_avatar_pngs(), cmd_face(), current_blobatar(), _extras_circle() (+43 more)

### Community 2 - "app.js"
Cohesion: 0.06
Nodes (83): acceptDrafts(), applyCustomFace(), applyDisplaysPayload(), applyFaceStatus(), applyObserveStatus(), autosize(), boot(), bufferToBase64() (+75 more)

### Community 3 - "memory.py"
Cohesion: 0.10
Nodes (36): capture_and_save_screen(), _capture_png(), capture_screen_png(), _condense_memories_impl(), _condense_worker(), _dated_heading_count(), _describe_screenshot(), _extract_run_memories_impl() (+28 more)

### Community 4 - "piper.py"
Cohesion: 0.31
Nodes (10): _ensure_voice_files(), _load(), _load_piper(), _onnx_path(), _pcm_to_wav(), Path, Piper local TTS (ONNX, CPU). ``synthesize_wav`` → WAV bytes., Synthesize ``text`` with Piper and return WAV bytes. (+2 more)

### Community 5 - "whisperflow.py"
Cohesion: 0.06
Nodes (47): _load_wav(), _log(), main(), _openai_model(), _provider_ready(), Path, race_once(), RaceResult (+39 more)

### Community 6 - "emit"
Cohesion: 0.16
Nodes (15): bind_events(), _default_logger(), emit(), Event, EventSink, get_events(), Any, BaseException (+7 more)

### Community 7 - "phone_gateway.py"
Cohesion: 0.07
Nodes (47): parse_reply_sink_param(), Parse optional API ``sink`` / ``speaker``. ``None`` / empty means this request…, read_phone_screen(), read_phone_speech(), advertise_urls(), audio_to_wav(), ensure_phone_gateway(), ingest_phone_audio() (+39 more)

### Community 8 - "log_overlay.py"
Cohesion: 0.08
Nodes (27): Ask the tray overlay to hide (True) or show (False) for a screenshot., set_overlay_hidden(), format_overlay_text(), overlay_enabled(), overlay_frame_top_left(), overlay_owner_alive(), overlay_should_show(), overlay_target_monitor() (+19 more)

### Community 9 - "wake.py"
Cohesion: 0.07
Nodes (47): _default_end_model_spec(), _default_phrase_for_models(), _default_wake_model(), _download_file(), _ensure_model(), format_end_listen_phrases(), format_listen_end_hint(), _format_phrase_list() (+39 more)

### Community 10 - "PhoneGatewayHttpTests"
Cohesion: 0.05
Nodes (8): AdvertiseUrlsTests, EnsureGatewayTests, PhoneAudioIngestTests, PhoneGatewayEnabledTests, PhoneGatewayHttpTests, PhoneGatewayTokenTests, PhonePhotoIngestTests, Phone gateway: env switch, auth, command queue (no live network bind required).

### Community 11 - "_listen_realtime_body"
Cohesion: 0.09
Nodes (36): consume_cancel(), True if Cancel was requested; clears the flag so it fires once., _cancel_pending(), _capture_sample_rate(), _emit_partial(), FanNoiseFilter, _float_to_pcm16_b64(), _float_to_wav() (+28 more)

### Community 12 - "skills.py"
Cohesion: 0.09
Nodes (48): _handle_read_skill(), cmd_condense_skills(), cmd_merge_skills(), _condense_one_skill(), condense_skills(), delete_skill_folder(), discover_skills(), format_skill_catalog() (+40 more)

### Community 13 - "read_status"
Cohesion: 0.08
Nodes (40): active_agents(), cmd_sleep(), format_tooltip(), Any, End the current listen immediately and transcribe what was captured., Soft-quit via flag, then SIGTERM the orchestrator process if known. Returns…, Plain-text tooltip for NSStatusItem hover., Snapshot for the tray (or callers). (+32 more)

### Community 14 - "chat_bridge.py"
Cohesion: 0.12
Nodes (27): Write a chat-attached PNG for the orchestrator; return basename for enqueue., save_chat_screenshot_png(), chat_bridge_enabled(), command_for_orchestrator(), delete_mcp_connection(), ensure_inbox_worker(), _face_option(), face_status_payload() (+19 more)

### Community 15 - "agent.py"
Cohesion: 0.11
Nodes (37): DesktopController, Wraps pyautogui with coordinate remapping between screenshot space and actual…, _action_summary(), confirm(), _confirm_terminal(), _extract_json_object(), _extract_memories_from_log(), _handle_ask_user() (+29 more)

### Community 16 - "kokoro.py"
Cohesion: 0.20
Nodes (17): _audio_from_result(), _ensure_misaki_en(), _ensure_mlx_g2p_fallback(), _float_to_wav(), _lang_code(), _load_mlx(), _load_onnx(), _pcm_to_wav() (+9 more)

### Community 17 - "orchestrator.py"
Cohesion: 0.05
Nodes (91): chat_text_only(), listen_pending(), log_llm(), phone_photo_pending(), quit_requested(), Put an LLM reply in the status log (and ``last_llm``) for the phone / tray., Chat turn with speaker off — reply in the UI, not via TTS or status blurbs., reply_tts_enabled() (+83 more)

### Community 18 - "cua.py"
Cohesion: 0.11
Nodes (35): _cleanup_side_processes(), _clear_pid_file(), cmd_install(), cmd_start(), cmd_status(), cmd_stop(), cua_on_path(), find_agent_pids() (+27 more)

### Community 19 - "_process_response"
Cohesion: 0.08
Nodes (23): User utterance plus each LLM step (replies, tool calls, results)., TurnTrace, _assistant_message_text(), _confirm_heard_enabled(), _give_response_closes_turn(), _looks_like_question(), _process_response(), Drain tool calls on `response` until the model stops calling tools. start_task… (+15 more)

### Community 20 - "ChatStore"
Cohesion: 0.08
Nodes (17): ChatRow, ChatStore, _connect(), _init_schema(), MessageRow, Path, Local SQLite chat history + screenshot files for the desktop chat UI., Thread-safe SQLite store for chats / messages / prefs. (+9 more)

### Community 21 - "checkpoint.py"
Cohesion: 0.07
Nodes (35): CheckpointResult, Any, Orchestrator turn checkpoint (harness-v2 §4). Between turns the lane passes a…, Run one orchestrator checkpoint before (or after recovering) a model call.…, run_orchestrator_checkpoint(), Live desktop snapshot attached to one orchestrator user turn., TurnDesktopContext, bind_next_run_queue() (+27 more)

### Community 22 - "displays.py"
Cohesion: 0.13
Nodes (37): _as_mapping(), assign_windows_to_monitors(), _cg_window_list(), _clip_url(), format_browser_tabs(), format_monitor_occupancy(), format_running_apps(), _frontmost_name() (+29 more)

### Community 23 - "LowLatencyTTS"
Cohesion: 0.10
Nodes (13): LowLatencyTTS, Thread-safe two-stage (synthesis → playback) streaming TTS pipeline., Reuse the process-wide persistent wake monitor (never stop it here)., Wake and/or keyboard interrupt event + release callback., Stop remaining synthesis/playback after a wake-word barge-in., Begin a streaming TTS session for ``response_id`` (public API)., Append plaintext to the active stream and queue speakable clauses., Finalize the active stream: flush remaining text into the synth queue. (+5 more)

### Community 24 - "MemoryStoreTests"
Cohesion: 0.06
Nodes (5): CondenseMemoryTests, ExtractMemoryTests, MemoryStoreTests, Tests for personal / app memory storage., TurnTraceTests

### Community 25 - ".do_POST"
Cohesion: 0.16
Nodes (21): accept_observe_draft(), _chat_row(), ChatBridgeHandler, displays_payload(), _json_body(), list_mcp_connections(), _msg_row(), observe_status_payload() (+13 more)

### Community 26 - "Focus"
Cohesion: 0.10
Nodes (8): Focus, SessionBuffer, ExcludeAppTests, FocusedDisplayCaptureTests, ObserverFlushTests, ParseExtractTests, Tests for the passive observer (session flush, drafts, accept)., SessionBufferTests

### Community 27 - "browser_data.py"
Cohesion: 0.06
Nodes (45): _apply_operation(), BrowserDataError, _chromium_binary(), _decode(), fetch_chromium(), fetch_lightpanda(), fetch_page(), _lightpanda_binary() (+37 more)

### Community 28 - "tts/__init__.py"
Cohesion: 0.12
Nodes (33): begin_tts_playback(), end_tts_playback(), Mark that Jarvis audio is synthesizing or playing (nested-safe)., Clear TTS activity when a synth/play scope exits., _apply_fade(), _numpy(), _phone_reply_sink(), _play_afplay() (+25 more)

### Community 29 - "tts_race.py"
Cohesion: 0.20
Nodes (22): _mlx_available(), Synthesize ``text`` with Kokoro and return WAV bytes., synthesize_wav(), _kokoro_voice(), _log(), main(), _openai_voice(), _piper_voice() (+14 more)

### Community 30 - "Session"
Cohesion: 0.07
Nodes (19): AudioSession, Any, Speak ``text``. On barge-in, listen and return the new command., Coordinate the audio devices for one orchestrator run., Capture a command after TTS barge-in (no second wake)., bind_session(), _canon(), Any (+11 more)

### Community 31 - "_user_turn_input"
Cohesion: 0.12
Nodes (13): _format_task_history(), _history_note(), build_system_prompt(), local_datetime_line(), Orchestrator system prompt (extracted from the turn loop)., One-line clock context injected on every orchestrator user turn., Assemble the orchestrator system prompt for one turn., Build Responses API ``input`` for one user turn (optional phone + desktop… (+5 more)

### Community 32 - "_create_response"
Cohesion: 0.11
Nodes (24): True when this turn was queued from the Electron chat app., reply_to_chat(), _create_response(), _exception_blob(), is_fatal_llm_error(), llm_error_speech(), LlmUnavailableError, _log_speaker_round() (+16 more)

### Community 33 - "llm_client.py"
Cohesion: 0.13
Nodes (27): _continue_response(), Follow-up Responses turn. DeepSeek must replay function_call items (stateless)., agent_provider(), fold_orphan_tool_outputs(), function_call_input_items(), input_has_image(), _item_call_id(), _item_output_text() (+19 more)

### Community 34 - "pid_alive"
Cohesion: 0.09
Nodes (32): pid_alive(), Show or hide the desktop chat window (tray menu / cua chat)., set_chat_app_pid(), set_chat_overlay_enabled(), ensure_chat_bridge(), Popen, Start the bridge subprocess if not already running., stop_chat_bridge() (+24 more)

### Community 35 - "tools_registry.py"
Cohesion: 0.13
Nodes (30): Brain, Follow-up user message so the model sees the read_screen PNG., read_screen_vision_input(), mcp_openai_tools(), agent_tools(), _entry(), execute_prepared_tool(), _execute_read_screen() (+22 more)

### Community 36 - "Path"
Cohesion: 0.14
Nodes (9): CondenseParseTests, CondenseRunTests, CuaSkillsCommandTests, DiscoverSkillsTests, MergeParseTests, MergeRunTests, Path, Tests for skill discovery and cua skills condense. (+1 more)

### Community 37 - "context.py"
Cohesion: 0.13
Nodes (23): desktop_logical_size(), format_display_context(), list_monitors(), Return attached displays with logical geometry (top-left origin). On macOS uses…, Human-readable display summary for the model’s starting context., assemble_context(), _capture_desktop_context(), capture_turn_desktop_context() (+15 more)

### Community 38 - "listen_once"
Cohesion: 0.10
Nodes (25): ask_user(), _consume_phone_utterance(), _end_phrase_live_enabled(), _EndPhraseWatcher, listen_and_confirm(), _listen_end_hint(), _listen_end_spotter(), listen_for_utterance() (+17 more)

### Community 39 - "FlagTests"
Cohesion: 0.07
Nodes (3): FlagTests, Tests for mark-done utterances and status flags., UtteranceTests

### Community 40 - "dictation_overlay.py"
Cohesion: 0.11
Nodes (17): dictation_overlay_enabled(), DictationDotsOverlay, dot_alphas(), hide_dictation_overlay(), init_dictation_overlay(), overlay_frame_near_point(), Any, Cursor overlay for Fn dictation: dots while holding, spinner after release. (+9 more)

### Community 41 - "evaluator.py"
Cohesion: 0.13
Nodes (28): AgentRoute, _client_for_model(), coach_agent(), _extract_json(), max_steps_for_difficulty(), model_for_recipe_handoff(), _progress_since_last_evaluation(), Any (+20 more)

### Community 42 - "speaker_id.py"
Cohesion: 0.07
Nodes (63): enroll_speaker_from_body(), cmd_delete(), cmd_enroll(), cmd_list(), cmd_test(), main(), OpenAI, Interactive speaker enrollment: read five passages (three long, two short),… (+55 more)

### Community 43 - "Any"
Cohesion: 0.22
Nodes (19): accept_draft(), _archive_draft(), cmd_accept(), cmd_list(), cmd_reject(), _find_drafts(), format_draft_listing(), list_proposed() (+11 more)

### Community 44 - "BrowserDataTests"
Cohesion: 0.10
Nodes (6): BrowserDataTests, _Headers, _Opener, dict, Tests for safe structured webpage retrieval., _Response

### Community 45 - "SpeakerIdTests"
Cohesion: 0.13
Nodes (8): AgentSpeakerContextTests, _alice_samples(), _mock_embed(), ndarray, Speaker ID unit tests (no microphone)., Deterministic fake embeddings: low freqs = speaker A, high = speaker B., _sine_wav(), SpeakerIdTests

### Community 46 - "test_actions.py"
Cohesion: 0.10
Nodes (7): FocusPreservationTests, KeypressBlockTests, MultiDisplayTests, Tests for desktop action helpers (typing, modifiers)., ReleaseModifiersTests, ScreenshotPublishTests, TypeModeTests

### Community 47 - "test_wake.py"
Cohesion: 0.08
Nodes (7): AfplayChimeTests, EndModelKeyTests, OverAndOutChimeTests, Wake-phrase stripping and listen-end spotting (no ONNX required)., StripTrailingTests, WakeIdentityTests, WakeSpotterTests

### Community 48 - "latency_report.py"
Cohesion: 0.19
Nodes (21): _append_trace(), build_report(), _durations(), finish_trace(), _fmt_ms(), _percentile(), Any, Path (+13 more)

### Community 49 - "test_orchestrator_task_guard.py"
Cohesion: 0.21
Nodes (15): _completed_task_match(), _completed_tasks_in_turn(), _normalized_task_goal(), Stable form for rejecting accidental post-completion relaunches., Return a completed near-duplicate from this orchestrator session., Pair start_task/result trace steps from only the current user turn., _start_task_block_reason(), test_awake_duplicate_is_still_blocked() (+7 more)

### Community 50 - "observe.py"
Cohesion: 0.15
Nodes (23): _capture_cg_display(), _capture_focused_display(), _capture_png(), _capture_png_bytes(), _capture_primary_png(), cmd_start(), cmd_status(), cmd_stop() (+15 more)

### Community 51 - "try_recipe"
Cohesion: 0.18
Nodes (17): format_recipe_catalog(), leftover_is_screenshot_only(), load_recipes(), maybe_save_recipe(), _maybe_save_recipe_impl(), pick_matching_recipe(), propose_recipe_llm(), Any (+9 more)

### Community 52 - "MainTests"
Cohesion: 0.09
Nodes (5): MainTests, Tests for the cua daemon CLI helpers., RunningPidTests, ShimTests, StartStopTests

### Community 53 - "test_tts_local.py"
Cohesion: 0.19
Nodes (7): KokoroSynthesizeTests, PiperSynthesizeTests, PiperVoicePathTests, Local Piper / Kokoro TTS adapters., _read_wav_frames(), en_US-lessac-medium → en/en_US/lessac/medium/en_US-lessac-medium.onnx, _voice_hf_path()

### Community 54 - "dictation.py"
Cohesion: 0.16
Nodes (20): cmd_start(), cmd_status(), cmd_stop(), dictation_enabled(), ensure_dictation_running(), _install_fn_tap(), _is_globe_fn_key(), _keystroke_v() (+12 more)

### Community 55 - "play_listen_end_chime"
Cohesion: 0.17
Nodes (12): _cue_listen_start(), Ping as soon as the STT stream is open — do not block capture., _afplay(), play_listen_end_chime(), play_listen_start_chime(), play_over_and_out_chime(), play_wake_chime(), Play a macOS system sound. Returns True if afplay was started. (+4 more)

### Community 56 - "mcp_auth.py"
Cohesion: 0.17
Nodes (21): build_oauth_provider(), cmd_mcp_status(), format_status(), _gh_bin(), _gh_login_browser(), _gh_token(), is_dcr_failure(), logged_in_names() (+13 more)

### Community 57 - "FileTokenStorage"
Cohesion: 0.27
Nodes (3): FileTokenStorage, Any, JSON token + client-info store (chmod 600).

### Community 58 - "utterance_match.py"
Cohesion: 0.33
Nodes (9): _bind_without_template(), parameterize_opened_url(), Replace task-specific bits in an opened URL with placeholders., content_words(), _extract_urls(), match_phrases_for(), _norm(), _phrase_in() (+1 more)

### Community 59 - "test_mcp.py"
Cohesion: 0.15
Nodes (4): ConfigTests, ConnectErrorIsolationTests, Tests for MCP config, read-only gating, and a live stdio echo server., ReadOnlyTests

### Community 60 - "accessibility.py"
Cohesion: 0.21
Nodes (19): accessibility_available(), _ax_frame(), _ax_get(), _ax_str(), _collect_lines(), _find_app(), focused_edit_info(), _frontmost_app() (+11 more)

### Community 61 - "actions.py"
Cohesion: 0.16
Nodes (16): capture_all_displays_enabled(), _capture_cg_display(), capture_displays_png(), capture_monitor_image(), desktop_logical_bounds(), Translates OpenAI computer-use actions into real mouse/keyboard input via…, Return (origin_x, origin_y, width, height) of the virtual desktop., PIL RGB image of one display, or None. (+8 more)

### Community 62 - "barge_router.py"
Cohesion: 0.12
Nodes (12): BargeDecision, classify_barge_utterance(), _extract_json(), Any, OpenAI, Classify TTS barge-in: new computer task vs answer/clarification., Result of LLM barge-in routing., Ask a cheap model whether a barge-in replaces the current work with a new task.… (+4 more)

### Community 63 - "mcp_client.py"
Cohesion: 0.26
Nodes (11): expand_env_value(), _expand_map(), _format_call_result(), McpTool, parse_mcp_arguments(), _parse_servers(), Any, MCP client for the voice orchestrator and computer-use agent. Load servers from… (+3 more)

### Community 64 - "task_feedback.py"
Cohesion: 0.17
Nodes (18): collect_post_task_feedback(), feedback_enabled(), interpret_feedback_text(), load_task_actions(), Any, OpenAI, Post-task user feedback: spoken prompt, persisted with goal and action log., Ask the user whether the task worked; persist with goal and actions. (+10 more)

### Community 65 - "_seed_dir"
Cohesion: 0.06
Nodes (13): TestCase, _FakeResponsesClient, GroundingTests, LlmFillTests, _log(), MatchTemplateTests, ProposeTests, Path (+5 more)

### Community 66 - "active_tts_voice"
Cohesion: 0.17
Nodes (14): LocalVoiceMappingTests, dict, patch, ActiveTtsVoiceTests, patch, Wake-word → Sarvam TTS speaker mapping., SpeakLaterTests, active_tts_voice() (+6 more)

### Community 67 - "_mcp_error_text"
Cohesion: 0.35
Nodes (6): _is_fatal(), _LiveServer, _mcp_error_text(), BaseException, Connect (or reconnect) a configured server. Returns an error string or None., stop_mcp()

### Community 68 - "resolve_agent_task"
Cohesion: 0.16
Nodes (11): _looks_like_agent_brief(), AgentTaskSpec, is_procedure_brief(), Planner vs actor: start_task is a goal, not a UI screenplay. The orchestrator…, True when the text is a how-to screenplay instead of a user goal., What the actor should match on vs what it should optimize for., Recipes match ``match_text`` (the spoken request). The computer-use prompt uses…, resolve_agent_task() (+3 more)

### Community 69 - "bus.py"
Cohesion: 0.13
Nodes (12): AgentMessageInbox, extract_jarvis_command(), ZeroMQ message bus: orchestrator → computer agent (while agent is running).…, Drain typed messages into steer / follow_up / next_run buckets., Return the command after a leading wake phrase, or None if absent. Kept for…, Agent side: non-blocking drain of queued orchestrator messages., Legacy: return steer + follow_up texts only (next_run excluded)., classify_utterance_for_agent() (+4 more)

### Community 70 - "test_displays.py"
Cohesion: 0.13
Nodes (7): _cg_window(), LiveLayoutMemorySkipTests, _monitor(), OccupancyFormatTests, Per-monitor window occupancy without requiring Quartz., RunningAppsAndTabsTests, WindowGeometryTests

### Community 71 - "._run_one"
Cohesion: 0.33
Nodes (5): ActionStopped, _is_blocked_chord(), normalize_key(), Exception, Raised when should_stop() fires mid-batch (wake word / quit).

### Community 72 - "main.js"
Cohesion: 0.19
Nodes (16): { app, BrowserWindow, ipcMain, shell, session, systemPreferences }, applyOverlayBehavior(), BRIDGE_PORT, bridgeRequest(), CONTROL_PORT, createWindow(), fs, hideMainWindow() (+8 more)

### Community 73 - "Recipe"
Cohesion: 0.17
Nodes (20): _bind_recipe(), extract_maps_place(), extract_media_query(), find_matching_recipe(), _has_map_word(), match_template(), _prelude_is_maps(), _prelude_is_youtube() (+12 more)

### Community 74 - "test_artifact_paths.py"
Cohesion: 0.25
Nodes (14): default_output_dir(), ensure_output_dir(), output_rule(), Path, Canonical paths for user-facing files created by the computer-use agent., Default destination unless the user explicitly names another location., format_not_to_do(), Always-on don'ts for the agent and orchestrator. (+6 more)

### Community 75 - "LiveDictationPaster"
Cohesion: 0.22
Nodes (5): _backspace_n(), LiveDictationPaster, Paste growing STT partials; revise via AX or backspace when text changes., Sync to the final transcript and restore the clipboard., Remove anything we inserted (cancel) and restore the clipboard.

### Community 76 - "recipes.py"
Cohesion: 0.16
Nodes (24): apply_params(), collect_logged_commands(), _computer_action_count(), _default_templates(), leftover_text(), _normalize_http_url(), open_app(), open_url() (+16 more)

### Community 77 - "test_low_latency_tts.py"
Cohesion: 0.33
Nodes (5): DecodedMessagePrefixTests, _engine(), PublicApiTests, patch, Unit tests for low-latency streaming TTS public API and helpers.

### Community 78 - "ConfigUpsertTests"
Cohesion: 0.13
Nodes (4): ConfigUpsertTests, Tests for MCP browser-login helpers (no live OAuth)., ResolveAppTests, TokenStorageTests

### Community 79 - "resolve_execution_route"
Cohesion: 0.24
Nodes (11): ExecutionRoute, _matching_recipe_name(), Deterministic fast/slow routing and specialist execution lanes. The router…, Choose a cheap first approach and the specialist prompt lane., resolve_execution_route(), test_browser_submission_uses_slow_path(), test_dense_cad_routes_to_visual_slow_path(), test_git_routes_to_terminal_fast_path() (+3 more)

### Community 80 - "Observer"
Cohesion: 0.26
Nodes (4): _append_events_log(), computer_use_active(), Observer, True while a computer-use job owns the pointer.

### Community 81 - "SimpleNamespace"
Cohesion: 0.17
Nodes (5): SimpleNamespace, FacePayloadTests, Chat bridge face overlay helpers., AssistantMessageTextTests, ChatTextOnlySpeakTests

### Community 82 - "speaker_output.py"
Cohesion: 0.18
Nodes (9): _app_playing(), media_playing(), _osascript(), Whether media is playing on the Mac — for the computer-use agent. Reports only…, True when Music or Spotify reports player state ``playing``., One-line status for the agent, or empty when disabled., speaker_output_block(), Media playing yes/no for the agent (no AppleScript in tests). (+1 more)

### Community 83 - "strip_wake_phrase"
Cohesion: 0.14
Nodes (16): _strip_listen_wake(), matches_wake_phrase(), normalize_speech_text(), _parse_wake_phrases(), _phrases_to_check(), Comma-separated wake phrases; longest-first friendly, case-preserving., True if transcript starts with (or equals) any configured wake phrase., Remove a leading wake phrase from a transcript (tries longest match first). (+8 more)

### Community 84 - "whoami.py"
Cohesion: 0.18
Nodes (8): who_am_i reads README.md for self-description., WhoAmITests, format_whoami_output(), Path, who_am_i tool: load this project's README so the agent can describe itself., Return README markdown with HTML stripped (demo embeds, etc.)., read_project_readme(), run_whoami_tool()

### Community 85 - "log"
Cohesion: 0.14
Nodes (24): enqueue_speak(), log(), Abort the current listen (no transcript) and stop in-flight agent work. While…, Append a line to the ring buffer shown on hover / in the menu., Queue a line for the orchestrator to speak (timer reminders, not user STT)., Ask the running computer-agent job to finish (menu bar or voice)., reply_sink(), request_cancel() (+16 more)

### Community 86 - "WakeMonitor"
Cohesion: 0.14
Nodes (6): Background wake-word listener for barge-in / idle wait. By default runs until…, Release the mic so STT (or another capture) can use it., Resume wake listening after STT (clears a stale woken flag)., Acknowledge a wake so listening can continue (persistent mode)., Block until woken (or should_stop / timeout). Assumes this monitor is already…, WakeMonitor

### Community 87 - ".listen_command"
Cohesion: 0.25
Nodes (8): Where the next TTS line should play: Mac speakers or the phone., Whether the current turn should speak replies (vs chat text only)., Tag the current orchestrator turn (chat / voice / phone / …)., set_reply_sink(), set_reply_tts(), set_turn_source(), Wake word → one cloud STT utterance. Returns None if stopped or empty., Capture a normal Jarvis command without requiring a wake word.

### Community 88 - "keyboard_barge.py"
Cohesion: 0.29
Nodes (11): acquire_tts_interrupt(), _drain_stdin(), _ensure_listener_locked(), _enter_cbreak(), keyboard_barge_enabled(), _listener_loop(), Keyboard barge-in during TTS (terminal key → stop speech → listen). When the…, Return ``(event, release)`` set when any source or a barge key fires. Always… (+3 more)

### Community 89 - "test_context.py"
Cohesion: 0.15
Nodes (4): ContextBundleTests, NotToDoTests, Ephemeral context bundle (not durable memory)., TurnDesktopContextTests

### Community 92 - "test_session_compact.py"
Cohesion: 0.15
Nodes (5): CheckpointTests, FoldTaskHistoryTests, FormatTaskHistoryTests, OverflowTests, Session compaction for orchestrator context limits.

### Community 94 - "package.json"
Cohesion: 0.17
Nodes (11): dependencies, electron, description, main, name, private, scripts, dev (+3 more)

### Community 95 - "Personal Computer Use Agent"
Cohesion: 0.17
Nodes (12): Durable memory store, Always-on computer-use policy, Isolated virtual desktop layer, HTTP-to-visible-browser escalation, Fast-path and slow-path execution router, MCP integrations, Personal Computer Use Agent, Computer-use safety and privacy controls (+4 more)

### Community 96 - "AskUserBridge"
Cohesion: 0.18
Nodes (6): AskUserBridge, Blocking ask_user from the agent worker thread to the orchestrator main thread.…, Called from the agent worker thread. Blocks until orchestrator replies., True if the agent has queued an ask_user the orchestrator hasn't taken yet., Called from the orchestrator. Returns {id, question} or None., Called from the orchestrator after speaking/listening.

### Community 97 - "low_latency.py"
Cohesion: 0.18
Nodes (9): concat_wavs(), Join WAV blobs that share the same format (streaming TTS chunks)., Print a ``[tts-latency] …`` line when TTS_LATENCY_LOG=1., tts_latency_print(), OpenAI, Path, Non-blocking, chunked TTS pipeline used by the voice orchestrator. Public API…, ensure_persistent_wake() (+1 more)

### Community 99 - "type_text"
Cohesion: 0.22
Nodes (10): _mac_type_paste(), _mac_type_unicode(), Paste via clipboard — fallback when Unicode injection fails in a field., Inject text into the focused control., How to inject text for computer-use ``type`` actions., Release common modifiers so the next keys go to the focused field, not…, Type via Unicode events — avoids virtual-key shortcuts (dictation, emoji…, release_stuck_modifiers() (+2 more)

### Community 100 - "LogOverlay"
Cohesion: 0.31
Nodes (3): LogOverlay, Click-through NSPanel. Construct only on the AppKit main thread., Take the panel off screen and release it (call on tray quit).

### Community 101 - "WindowBuffer"
Cohesion: 0.24
Nodes (3): Accumulates closed sessions until OBSERVE_DRAFT_SECONDS have elapsed., WindowBuffer, WindowBufferTests

### Community 102 - "fill_recipe_slots_llm"
Cohesion: 0.24
Nodes (10): _extract_json_object(), fill_recipe_slots(), fill_recipe_slots_llm(), params_grounded(), True when the slot is actually present in this request (not a prior place)., Short remainder after a URL open — never 'create a new tab / navigate'., Fill {{placeholders}}. Regex first; EVAL_MODEL only if bind fails., _recipe_slot_names() (+2 more)

### Community 103 - "tts_print"
Cohesion: 0.29
Nodes (9): get_client(), Shared SarvamAI client (STT + TTS)., Print a ``[tts] …`` line when TTS_LOG=1 (or ``force`` for real errors)., tts_print(), _pcm_to_wav(), Sarvam AI Bulbul text-to-speech (HTTP streaming → WAV)., Stream speech via Sarvam ``convert_stream`` (linear16) and return a WAV. Uses…, _split_text() (+1 more)

### Community 104 - "webmcp_chromium.mjs"
Cohesion: 0.29
Nodes (7): command(), deadlineMs, execute(), pending, run(), start(), startup

### Community 106 - "PhoneTtsSinkTests"
Cohesion: 0.31
Nodes (3): PhoneTtsSinkTests, Phone reply sink: synthesize on Mac, skip afplay, publish WAV., _silence_wav()

### Community 108 - "CallbackServer"
Cohesion: 0.25
Nodes (3): AbstractEventLoop, CallbackServer, Local HTTP listener for the OAuth redirect.

### Community 109 - "DictationDaemon"
Cohesion: 0.25
Nodes (4): DictationDaemon, Switch dots ↔ spinner without hiding. No-op if the overlay is down., set_dictation_overlay_style(), Handle Fn alone edge. Returns True if the event should be swallowed.

### Community 110 - "stt/__init__.py"
Cohesion: 0.07
Nodes (38): _cancel_requested(), choose_transcript(), classify_yes_no(), _dictation_provider(), _event_delta(), _event_transcript(), _event_type(), _model_supports_turn_detection() (+30 more)

### Community 111 - "TaskLog"
Cohesion: 0.18
Nodes (8): _jsonable(), Any, Path, Compact transcript for skill-proposal and memory-extract prompts., Append-only log for a single agent run., TaskLog, MaybeCreateSkillTests, maybe_create_skill must not block the agent / last TTS.

### Community 112 - "echo_mcp_server.py"
Cohesion: 0.32
Nodes (7): add(), delete_item(), echo(), Minimal stdio MCP server used by tests/test_mcp.py., Return the same text., Delete an item by id (write)., tool

### Community 113 - "load_dotenv"
Cohesion: 0.33
Nodes (6): configure_native_threads(), load_dotenv(), Path, Load a local .env into os.environ (no external dependency)., Cap BLAS/OpenMP threads before numpy/OpenBLAS loads. Unbounded OpenBLAS…, Parse KEY=VALUE lines from `.env` into the process environment. By default does…

### Community 114 - "terminal.py"
Cohesion: 0.43
Nodes (6): _decode(), _format_report(), Run local shell commands for the computer-use agent. Captures stdout/stderr…, Execute `command` via the user's shell and return a text report. Uses the shell…, run_command(), _truncate()

### Community 115 - "McpManager"
Cohesion: 0.19
Nodes (7): get_manager(), load_mcp_config(), McpManager, Path, Long-lived MCP sessions on a background asyncio loop., ServerSpec, start_mcp()

### Community 118 - "main"
Cohesion: 0.29
Nodes (8): cmd_help(), format_help(), main(), Full CLI reference for ``cua help``., cmd_mcp_login(), cmd_mcp_logout(), format_apps_help(), logout_app()

### Community 119 - "._to_screen_coords"
Cohesion: 0.40
Nodes (4): Map list_monitors() desktop space → CGEvent / pyautogui (origin = main display)., Map list_monitors() desktop space → CGEvent / pyautogui (origin = main display)., Map screenshot pixels → pyautogui points (main-display origin)., to_pyautogui_coords()

### Community 120 - "test_stt_phone.py"
Cohesion: 0.29
Nodes (3): AskUserTests, ListenOncePhoneTests, Phone-queued text must be accepted while STT is listening (ask_user).

### Community 121 - "netflix-resume-continue-watching"
Cohesion: 0.50
Nodes (4): Netflix Continue Watching, netflix-resume-continue-watching, Most-recent media resumption, resume-paused-media-across-apps

### Community 122 - "organize-downloads-by-extension"
Cohesion: 0.33
Nodes (6): Metadata-preserving category move, move-downloads-categories-to-desktop, Safe extension-based Desktop organization, organize-desktop-by-extension, Safe extension-based Downloads organization, organize-downloads-by-extension

### Community 123 - "list_speaker_payload"
Cohesion: 0.50
Nodes (3): list_speaker_payload(), Speaker list payload for the Electron manage-speakers page., SpeakerPayloadTests

### Community 124 - "listen_dictation"
Cohesion: 0.40
Nodes (5): listen_dictation(), Path, Write captured mic audio (and optional transcript) under recordings/., Hold-to-talk dictation with live partials; ends on Fn release (Send), not…, save_recording()

### Community 126 - "task_log.py"
Cohesion: 0.38
Nodes (6): Update high-level status shown in the menu bar., Set state and append the same message to the log ring., set_and_log(), set_state(), _project(), Per-task run logging: records agent messages, tool calls, and computer actions.

### Community 128 - "Email snapshot schema"
Cohesion: 0.60
Nodes (5): Email snapshot schema, gmail-extract-latest-10-emails, gmail-extract-todays-emails, Email importance heuristics, gmail-flag-today-important-and-screenshot

### Community 129 - "synthesize_wav"
Cohesion: 0.50
Nodes (4): OpenAI, OpenAI text-to-speech (gpt-4o-mini-tts, with tts-1-hd fallback)., Return WAV bytes from OpenAI speech synthesis., synthesize_wav()

### Community 130 - "_scroll"
Cohesion: 0.50
Nodes (4): _mac_scroll_pixels(), Post trackpad-like continuous pixel scroll events via Quartz. pyautogui's line-…, Scroll by approximate pixel deltas. dy>0 scrolls content up (wheel up)., _scroll()

### Community 131 - "Electronic Basics #1: The Multimeter by GreatScott!"
Cohesion: 0.50
Nodes (4): Electronic Basics #1: The Multimeter by GreatScott!, Agent confirms video playback and audible audio, VS Code screenshot demonstrating the computer-use-agent project, YouTube search, selection, and tutorial playback skill

### Community 132 - "find-jobs-matching-profile"
Cohesion: 0.50
Nodes (4): Job match scoring, find-jobs-matching-profile, LinkedIn post analytics, linkedin-capture-latest-post-analytics

### Community 133 - "Bluetooth Low Energy GATT"
Cohesion: 0.83
Nodes (4): Bluetooth Low Energy GATT, ESP32, iDotMatrix protocol, idotmatrix-ble-detection

### Community 134 - "open-app"
Cohesion: 0.50
Nodes (4): open-app, Spotlight application launch, MCP-first web search, web-search

### Community 135 - "preview-open-and-zoom-image"
Cohesion: 0.50
Nodes (4): Preview Actual Size viewing, preview-open-and-zoom-image, Hardware pin identification, read-diagram-on-display-and-report-pins

### Community 136 - "remove-third-party-keypress-sound"
Cohesion: 0.50
Nodes (4): Login-item and audio-agent cleanup, remove-third-party-keypress-sound, Process audio isolation, stop-terminal-audio-process

### Community 137 - "rename-images-by-content"
Cohesion: 0.50
Nodes (4): Content-derived image naming, rename-images-by-content, Representative-frame video classification, rename-videos-by-content

### Community 138 - "start-whatsapp-video-call-desktop"
Cohesion: 0.50
Nodes (4): start-whatsapp-video-call-desktop, WhatsApp Desktop video call, whatsapp-call-contact, WhatsApp Desktop contact call

### Community 139 - "web-form-fill-attach-resume-and-pause"
Cohesion: 0.50
Nodes (4): Pre-submission review gate, web-form-fill-attach-resume-and-pause, web-form-submit-capture-confirmation, Submission confirmation evidence

### Community 142 - "Path"
Cohesion: 0.14
Nodes (34): list_memories_payload(), Replace a memory file's markdown contents (full-file edit)., write_memory_payload(), apply_condensed_memory_files(), apply_extracted_memory_items(), _canonical_kind(), ensure_memory_dirs(), _is_live_layout_memory() (+26 more)

### Community 143 - "Text-to-speech output from speakers re-triggers the microphone wake detector"
Cohesion: 0.67
Nodes (3): Mitigate false wake triggers by avoiding the wake phrase in spoken text and disabling barge-in on phrase matches, Text-to-speech output from speakers re-triggers the microphone wake detector, Wake phrase configuration through WAKE_PHRASE environment variable

### Community 144 - "diagramsnet-create-and-export-diagram"
Cohesion: 0.67
Nodes (3): diagramsnet-create-and-export-diagram, diagramsnet-create-pcb-pinout-from-image, diagramsnet-edit-and-export-drawio

### Community 145 - "git-merge-branch-into-main-with-backup"
Cohesion: 0.67
Nodes (3): Timestamped safety branch, git-merge-branch-into-main-with-backup, github-delete-branch-via-ui

### Community 146 - "github-create-issues-from-plan-md"
Cohesion: 0.67
Nodes (3): Issue creation confirmation gate, github-create-issues-from-plan-md, github-find-own-repo-and-star-count

### Community 147 - "google-maps-open-place"
Cohesion: 0.67
Nodes (3): google-maps-get-directions, google-maps-open-place, google-maps-show-national-parks-country

### Community 148 - "hardware-control-via-mcp"
Cohesion: 0.67
Nodes (3): MCP hardware control, Read-before-write device control, hardware-control-via-mcp

### Community 149 - "hn-submit-repo"
Cohesion: 0.67
Nodes (3): hn-comments, hn-edit-submission, hn-submit-repo

### Community 150 - "india-quarterly-gdp-by-sector-piechart"
Cohesion: 0.67
Nodes (3): Gross Value Added at basic prices, Ministry of Statistics and Programme Implementation, india-quarterly-gdp-by-sector-piechart

### Community 151 - "manga-chapter-spoiler-verify-and-summarize"
Cohesion: 0.67
Nodes (3): manga-chapter-spoiler-verify-and-summarize, Independent-source spoiler cross-checking, medium-trending-extract-top-articles

### Community 169 - "convert-chart-figures-to-usd/SKILL.md"
Cohesion: 0.33
Nodes (5): Read and parse lines like: Label: ₹12,000 crore  OR  Label: 12,000 (assume unit comment), Replace the line above with manual setting if you pasted rate; or instead run interactively to set `rate`., Steps, Tips, When not to use this skill

### Community 170 - "cursor-generate-project-from-prompt/SKILL.md"
Cohesion: 0.40
Nodes (4): Failure modes and recovery, Steps, Tips, When to use this skill

### Community 171 - "disable-terminal-bell-and-system-ui-sounds/SKILL.md"
Cohesion: 0.50
Nodes (3): Example quick checklist to include in your report, Steps, Tips

## Knowledge Gaps
- **100 isolated node(s):** `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path`, `http`, `BRIDGE_PORT` (+95 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1164 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **42 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_status()` connect `read_status` to `app_status.py`, `face_overlay.py`, `pid_alive`, `phone_gateway.py`, `log_overlay.py`, `wake.py`, `DictationDaemon`, `chat_bridge.py`, `Observer`, `orchestrator.py`, `cua.py`, `observe.py`, `dictation.py`, `.do_POST`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `load_dotenv()` connect `load_dotenv` to `memory.py`, `whisperflow.py`, `skills.py`, `read_status`, `chat_bridge.py`, `agent.py`, `orchestrator.py`, `cua.py`, `observe.py`, `dictation.py`, `tts_race.py`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `LowLatencyTTS` connect `LowLatencyTTS` to `_create_response`, `orchestrator.py`, `test_low_latency_tts.py`, `low_latency.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **What connects `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path` to the rest of the system?**
  _100 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `app_status.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05379746835443038 - nodes in this community are weakly interconnected._
- **Should `face_overlay.py` be split into smaller, more focused modules?**
  _Cohesion score 0.050156739811912224 - nodes in this community are weakly interconnected._
- **Should `app.js` be split into smaller, more focused modules?**
  _Cohesion score 0.06368330464716007 - nodes in this community are weakly interconnected._