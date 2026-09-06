# Graph Report - computer-use-agent  (2026-09-06)

## Corpus Check
- 233 files · ~213,238 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3711 nodes · 8314 edges · 205 communities (154 shown, 50 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 303 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d49d0ff4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- llm_trace.py
- face_overlay.py
- app.js
- speak
- status_control.py
- stt_race.py
- pid_alive
- task_feedback.py
- log_overlay.py
- wake.py
- PhoneGatewayHttpTests
- stt/__init__.py
- skills.py
- tts_race.py
- OpenAI
- agent.py
- cua.py
- read_status
- checkpoint.py
- test_orchestrator_questions.py
- ChatStore
- _launch_agent_job
- displays.py
- LowLatencyTTS
- MemoryStoreTests
- chat_bridge.py
- Focus
- browser_data.py
- tts/__init__.py
- strip_wake_phrase
- Session
- context.py
- _create_response
- llm_client.py
- test_chat_llm.py
- tools_registry.py
- Path
- speaker_enroll.py
- orchestrator.py
- FlagTests
- dictation_overlay.py
- evaluator.py
- Recipe
- PhoneTtsSinkTests
- _Response
- SpeakerIdTests
- test_actions.py
- test_wake.py
- latency_report.py
- TurnTrace
- memory_graph.py
- parse_json_dict
- MainTests
- _StreamSession
- dictation.py
- low_latency.py
- mcp_auth.py
- FileTokenStorage
- mcp_client.py
- LiveStdioTests
- accessibility.py
- observe.py
- barge_router.py
- kokoro.py
- piper.py
- _seed_dir
- active_tts_voice
- McpManager
- resolve_agent_task
- resolve_execution_route
- .feed
- phone_gateway.py
- main.js
- resolve_blobatar
- test_artifact_paths.py
- LiveDictationPaster
- recipes.py
- ._run_one
- ConfigUpsertTests
- running_pid
- Observer
- session_compact.py
- speaker_output.py
- test_displays.py
- whoami.py
- timers.py
- WakeMonitor
- test_face_overlay.py
- keyboard_barge.py
- test_context.py
- FnFlagTests
- TaskLog
- test_session_compact.py
- ChatBridgeHandler
- package.json
- Personal Computer Use Agent
- LogOverlay
- SimpleNamespace
- BrowserDataTests
- format_monitor_occupancy
- speaker_id.py
- WindowBuffer
- DraftAcceptTests
- app_status.py
- webmcp_chromium.mjs
- ChatStreamTests
- list_speaker_payload
- ToolRegistryTests
- CallbackServer
- .on_fn_edge
- _listen_record_then_transcribe
- open-meteo-current-weather-report/SKILL.md
- echo_mcp_server.py
- test_harness_structure.py
- terminal.py
- try_recipe
- current_blobatar
- OverlayFrameTests
- tts_print
- load_dotenv
- test_stt_phone.py
- netflix-resume-continue-watching
- organize-downloads-by-extension
- FaceOverlay
- run_prelude
- detect-usb-serial-bridges/SKILL.md
- LlmClientTests
- ChatScreenshotTurnTests
- Email snapshot schema
- GraphMemoryTests
- face_mood_for_state
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
- FanNoiseFilter
- memory.py
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
- live-device-scan-loop/SKILL.md
- _supervise_agent
- convert-chart-figures-to-usd/SKILL.md
- cursor-generate-project-from-prompt/SKILL.md
- disable-terminal-bell-and-system-ui-sounds/SKILL.md
- type_text
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
- status_tray_controller.py
- open-diagrams-from-folder/SKILL.md
- actions.py
- MatchTemplateTests
- format_scheduled_tasks
- save-and-preview-svg/SKILL.md
- upwork-evaluate-and-apply/SKILL.md
- upwork-update-profile-from-resume/SKILL.md
- SmartTurnClassifier
- FacePayloadTests
- mood_eye_pose
- ScheduledTaskTests
- ChatBridgeQueueTests
- scheduled_tasks.py
- test_recipes.py
- audio.py
- _FakeResponsesClient
- ComputerUseGateTests
- conftest.py
- UrlSafetyTests

## God Nodes (most connected - your core abstractions)
1. `read_status()` - 59 edges
2. `TaskLog` - 47 edges
3. `_read()` - 45 edges
4. `TrayController` - 40 edges
5. `_write()` - 36 edges
6. `LowLatencyTTS` - 33 edges
7. `ChatBridgeHandler` - 32 edges
8. `pid_alive()` - 32 edges
9. `_supervise_agent()` - 31 edges
10. `_process_response()` - 31 edges

## Surprising Connections (you probably didn't know these)
- `_print_and_log_messages()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `_handle_ask_user()` --calls--> `is_mark_done_utterance()`  [INFERRED]
  agent.py → status_control.py
- `_handle_ask_user()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `_handle_list_skills()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `_handle_read_skill()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py

## Import Cycles
- None detected.

## Communities (205 total, 50 thin omitted)

### Community 0 - "llm_trace.py"
Cohesion: 0.06
Nodes (70): _attach_llm_trace(), bind_events(), _default_logger(), Event, EventSink, get_events(), Any, BaseException (+62 more)

### Community 1 - "face_overlay.py"
Cohesion: 0.24
Nodes (17): cmd_face(), _extras_circle(), _feed(), _finalize(), format_blobatar_list(), _hashed_blobatar(), _i32(), _imul() (+9 more)

### Community 2 - "app.js"
Cohesion: 0.06
Nodes (85): acceptDrafts(), applyCustomFace(), applyDisplaysPayload(), applyFaceStatus(), applyObserveStatus(), autosize(), boot(), bufferToBase64() (+77 more)

### Community 3 - "speak"
Cohesion: 0.12
Nodes (24): enabled(), set_last_speaker(), ask_user(), choose_transcript(), _consume_phone_utterance(), listen_and_confirm(), listen_once(), _normalize_reply() (+16 more)

### Community 4 - "status_control.py"
Cohesion: 0.09
Nodes (51): _cleanup_agent_run(), ModuleType, apply_control(), active_agents(), cancel_pending(), clear_cancel(), clear_mark_done(), clear_quit_request() (+43 more)

### Community 5 - "stt_race.py"
Cohesion: 0.06
Nodes (46): _load_wav(), _log(), main(), _openai_model(), _provider_ready(), Path, race_once(), RaceResult (+38 more)

### Community 6 - "pid_alive"
Cohesion: 0.13
Nodes (24): set_chat_app_pid(), ensure_chat_bridge(), Popen, Start the bridge subprocess if not already running., stop_chat_bridge(), cmd_chat(), _control_chat_app(), _electron_bin() (+16 more)

### Community 7 - "task_feedback.py"
Cohesion: 0.15
Nodes (20): classify_yes_no(), Return 'yes', 'no', 'quit', 'retry', or None if unclear., collect_post_task_feedback(), feedback_enabled(), interpret_feedback_text(), load_task_actions(), Any, OpenAI (+12 more)

### Community 8 - "log_overlay.py"
Cohesion: 0.09
Nodes (25): format_overlay_text(), overlay_enabled(), overlay_frame_top_left(), overlay_owner_alive(), overlay_should_show(), overlay_target_monitor(), pause_overlay_for_capture(), _post_overlay_note() (+17 more)

### Community 9 - "wake.py"
Cohesion: 0.06
Nodes (53): _afplay(), _default_end_model_spec(), _default_phrase_for_models(), _default_wake_model(), _download_file(), _ensure_model(), format_end_listen_phrases(), format_listen_end_hint() (+45 more)

### Community 10 - "PhoneGatewayHttpTests"
Cohesion: 0.05
Nodes (8): AdvertiseUrlsTests, EnsureGatewayTests, PhoneAudioIngestTests, PhoneGatewayEnabledTests, PhoneGatewayHttpTests, PhoneGatewayTokenTests, PhonePhotoIngestTests, Phone gateway: env switch, auth, command queue (no live network bind required).

### Community 11 - "stt/__init__.py"
Cohesion: 0.07
Nodes (54): _cancel_pending(), _cancel_requested(), _capture_sample_rate(), _cue_listen_start(), _emit_partial(), _event_delta(), _event_transcript(), _event_type() (+46 more)

### Community 12 - "skills.py"
Cohesion: 0.10
Nodes (44): _handle_read_skill(), parse_json_object(), Parse a JSON value, including one buried in surrounding prose., _condense_one_skill(), condense_skills(), delete_skill_folder(), discover_skills(), format_skill_catalog() (+36 more)

### Community 13 - "tts_race.py"
Cohesion: 0.19
Nodes (23): sarvam_configured(), _mlx_available(), Synthesize ``text`` with Kokoro and return WAV bytes., synthesize_wav(), _kokoro_voice(), _log(), main(), _openai_voice() (+15 more)

### Community 14 - "OpenAI"
Cohesion: 0.12
Nodes (33): chat_text_only(), log_llm(), Put an LLM reply in the status log (and ``last_llm``) for the phone / tray., Chat turn with speaker off — reply in the UI, not via TTS or status blurbs., reply_tts_enabled(), set_last_spoken(), get_audio(), _handle_tool() (+25 more)

### Community 15 - "agent.py"
Cohesion: 0.08
Nodes (51): DesktopController, Wraps pyautogui with coordinate remapping between screenshot space and actual…, _action_summary(), _agent_one_turn(), _agent_prompt_body(), _bootstrap_agent_run(), _collect_computer_outputs(), _collect_desktop_outputs() (+43 more)

### Community 16 - "cua.py"
Cohesion: 0.15
Nodes (27): ArgumentParser, _build_parser(), _cmd_chat(), _cmd_face(), cmd_help(), cmd_install(), _cmd_restart(), _cmd_sleep() (+19 more)

### Community 17 - "read_status"
Cohesion: 0.12
Nodes (8): ack_overlay_hidden(), Snapshot for the tray (or callers)., Tray confirms the panel is actually off-screen (or back)., read_status(), NSObject, python_method, Main-thread entry for SIGTERM/SIGINT (see _signal_quit)., TrayController

### Community 18 - "checkpoint.py"
Cohesion: 0.07
Nodes (28): AgentMessageInbox, AgentMessagePublisher, extract_jarvis_command(), ZeroMQ message bus: orchestrator → computer agent (while agent is running).…, Return the command after a leading wake phrase, or None if absent. Kept for…, Orchestrator side: enqueue user directives for a running agent., Agent side: non-blocking drain of queued orchestrator messages., Legacy: return steer + follow_up texts only (next_run excluded). (+20 more)

### Community 19 - "test_orchestrator_questions.py"
Cohesion: 0.10
Nodes (15): _give_response_closes_turn(), _looks_like_question(), Build Responses API ``input`` for one user turn (optional phone + desktop…, True when spoken text expects a reply (so we must open the mic)., Drop trailing 'I'll wait / I'm ready' padding from a spoken reply., True if give_response_to_user spoke after `start_index` (this response only)., True when a statement was spoken and the model must not talk again., _strip_wait_filler() (+7 more)

### Community 20 - "ChatStore"
Cohesion: 0.07
Nodes (17): ChatRow, ChatStore, _connect(), _init_schema(), MessageRow, Path, Local SQLite chat history + screenshot files for the desktop chat UI., Thread-safe SQLite store for chats / messages / prefs. (+9 more)

### Community 21 - "_launch_agent_job"
Cohesion: 0.10
Nodes (16): AskUserBridge, Blocking ask_user from the agent worker thread to the orchestrator main thread.…, Called from the agent worker thread. Blocks until orchestrator replies., True if the agent has queued an ask_user the orchestrator hasn't taken yet., Called from the orchestrator. Returns {id, question} or None., Called from the orchestrator after speaking/listening., current_trace_id(), AgentJob (+8 more)

### Community 22 - "displays.py"
Cohesion: 0.21
Nodes (24): _as_mapping(), assign_windows_to_monitors(), _cg_window_list(), _clip_url(), format_browser_tabs(), frontmost_window_info(), _keep_window(), list_windows_by_monitor() (+16 more)

### Community 23 - "LowLatencyTTS"
Cohesion: 0.09
Nodes (15): LowLatencyTTS, OpenAI, Path, Thread-safe two-stage (synthesis → playback) streaming TTS pipeline., Reuse the process-wide persistent wake monitor (never stop it here)., Wake and/or keyboard interrupt event + release callback., Stop remaining synthesis/playback after a wake-word barge-in., Begin a streaming TTS session for ``response_id`` (public API). (+7 more)

### Community 24 - "MemoryStoreTests"
Cohesion: 0.05
Nodes (5): CondenseMemoryTests, ExtractMemoryTests, MemoryStoreTests, Tests for personal / app memory storage., TurnTraceTests

### Community 25 - "chat_bridge.py"
Cohesion: 0.09
Nodes (48): Show or hide the top-center face panel (tray menu toggle)., Write a chat-attached PNG for the orchestrator; return basename for enqueue., save_chat_screenshot_png(), set_face_overlay_enabled(), accept_observe_draft(), cancel_scheduled_queue_item(), chat_bridge_enabled(), delete_mcp_connection() (+40 more)

### Community 26 - "Focus"
Cohesion: 0.11
Nodes (7): Focus, SessionBuffer, ExcludeAppTests, FocusedDisplayCaptureTests, ObserverFlushTests, Tests for the passive observer (session flush, drafts, accept)., SessionBufferTests

### Community 27 - "browser_data.py"
Cohesion: 0.06
Nodes (50): _apply_operation(), BrowserDataError, _chromium_binary(), _decode(), discover_endpoints(), _discovery_terms(), _endpoint_score(), fetch_chromium() (+42 more)

### Community 28 - "tts/__init__.py"
Cohesion: 0.13
Nodes (27): _apply_fade(), _numpy(), _phone_reply_sink(), _play_afplay(), _play_sounddevice(), play_wav(), OpenAI, Path (+19 more)

### Community 29 - "strip_wake_phrase"
Cohesion: 0.14
Nodes (16): _strip_listen_wake(), matches_wake_phrase(), normalize_speech_text(), _parse_wake_phrases(), _phrases_to_check(), Comma-separated wake phrases; longest-first friendly, case-preserving., True if `text` contains any configured wake phrase (TTS echo guard)., True if transcript starts with (or equals) any configured wake phrase. (+8 more)

### Community 30 - "Session"
Cohesion: 0.10
Nodes (13): bind_session(), _canon(), Any, Explicit voice-session phases. Tray status is a projection of this machine.…, Illegal phase transition (strict mode only)., In-process session. ``enter`` writes the tray JSON via app_status., Move to ``phase``. Returns the phase actually entered., Install the process-wide session. Pass None to clear. (+5 more)

### Community 31 - "context.py"
Cohesion: 0.14
Nodes (22): assemble_context(), _capture_desktop_context(), capture_turn_desktop_context(), _clip(), ContextBundle, format_not_to_do(), _orchestrator_desktop_ax_enabled(), orchestrator_desktop_enabled() (+14 more)

### Community 32 - "_create_response"
Cohesion: 0.12
Nodes (22): _announce_llm_failure(), _create_response(), _exception_blob(), _execute_create_response(), is_fatal_llm_error(), llm_error_speech(), LlmUnavailableError, main() (+14 more)

### Community 33 - "llm_client.py"
Cohesion: 0.12
Nodes (28): _initial_api_input(), _run_agent_session(), agent_provider(), fold_orphan_tool_outputs(), function_call_input_items(), input_has_image(), _item_call_id(), _item_output_text() (+20 more)

### Community 34 - "test_chat_llm.py"
Cohesion: 0.10
Nodes (18): command_for_orchestrator(), chat_overlay_enabled(), chat_overlay_env_enabled(), chat_should_show(), command_for_orchestrator(), Any, Tray poll: ensure an enabled chat exists; disabled chats stay warm., True when the chat window should be shown (tray / cua chat / env). (+10 more)

### Community 35 - "tools_registry.py"
Cohesion: 0.14
Nodes (28): Brain, mcp_openai_tools(), agent_tools(), _entry(), execute_prepared_tool(), _execute_read_screen(), finalize_tool_outcome(), ImmediateToolOutcome (+20 more)

### Community 36 - "Path"
Cohesion: 0.14
Nodes (9): CondenseParseTests, CondenseRunTests, CuaSkillsCommandTests, DiscoverSkillsTests, MergeParseTests, MergeRunTests, Path, Tests for skill discovery and cua skills condense. (+1 more)

### Community 37 - "speaker_enroll.py"
Cohesion: 0.16
Nodes (26): enroll_speaker_from_body(), _dispatch_speaker(), cmd_delete(), cmd_enroll(), cmd_list(), cmd_test(), main(), OpenAI (+18 more)

### Community 38 - "orchestrator.py"
Cohesion: 0.05
Nodes (48): registry_traces_tool(), is_save_screen_utterance(), True when the user wants the current display stored as memory., _assistant_message_text(), _exit_on_signal(), _finish_scheduled_turn(), _format_task_history(), _handle_voice_shortcut() (+40 more)

### Community 39 - "FlagTests"
Cohesion: 0.07
Nodes (3): FlagTests, Tests for mark-done utterances and status flags., UtteranceTests

### Community 40 - "dictation_overlay.py"
Cohesion: 0.11
Nodes (17): dictation_overlay_enabled(), DictationDotsOverlay, dot_alphas(), hide_dictation_overlay(), init_dictation_overlay(), overlay_frame_near_point(), Any, Cursor overlay for Fn dictation: dots while holding, spinner after release. (+9 more)

### Community 41 - "evaluator.py"
Cohesion: 0.12
Nodes (30): AgentRoute, _client_for_model(), coach_agent(), _extract_json(), max_steps_for_difficulty(), model_for_recipe_handoff(), _progress_since_last_evaluation(), Any (+22 more)

### Community 42 - "Recipe"
Cohesion: 0.17
Nodes (21): _bind_recipe(), _bind_without_template(), extract_maps_place(), extract_media_query(), find_matching_recipe(), _has_map_word(), match_template(), _prelude_is_maps() (+13 more)

### Community 43 - "PhoneTtsSinkTests"
Cohesion: 0.31
Nodes (3): PhoneTtsSinkTests, Phone reply sink: synthesize on Mac, skip afplay, publish WAV., _silence_wav()

### Community 44 - "_Response"
Cohesion: 0.16
Nodes (5): _Headers, _Opener, dict, Tests for safe structured webpage retrieval., _Response

### Community 45 - "SpeakerIdTests"
Cohesion: 0.13
Nodes (8): AgentSpeakerContextTests, _alice_samples(), _mock_embed(), ndarray, Speaker ID unit tests (no microphone)., Deterministic fake embeddings: low freqs = speaker A, high = speaker B., _sine_wav(), SpeakerIdTests

### Community 46 - "test_actions.py"
Cohesion: 0.08
Nodes (8): FocusPreservationTests, KeypressBlockTests, MultiDisplayTests, Tests for desktop action helpers (typing, modifiers)., ReleaseModifiersTests, ScreenshotPublishTests, TypeModeTests, TypeTextTests

### Community 47 - "test_wake.py"
Cohesion: 0.08
Nodes (7): AfplayChimeTests, EndModelKeyTests, OverAndOutChimeTests, Wake-phrase stripping and listen-end spotting (no ONNX required)., StripTrailingTests, WakeIdentityTests, WakeSpotterTests

### Community 48 - "latency_report.py"
Cohesion: 0.18
Nodes (21): _append_trace(), build_report(), _durations(), finish_trace(), _fmt_ms(), _percentile(), Any, Path (+13 more)

### Community 49 - "TurnTrace"
Cohesion: 0.14
Nodes (18): User utterance plus each LLM step (replies, tool calls, results)., TurnTrace, _completed_task_match(), _completed_tasks_in_turn(), _normalized_task_goal(), Stable form for rejecting accidental post-completion relaunches., Return a completed near-duplicate from this orchestrator session., Pair start_task/result trace steps from only the current user turn. (+10 more)

### Community 50 - "memory_graph.py"
Cohesion: 0.16
Nodes (26): datetime, apply_observation_graph(), _claim_id(), _clean_entity(), compact_graph(), _connect(), database_path(), export_graphify() (+18 more)

### Community 51 - "parse_json_dict"
Cohesion: 0.19
Nodes (13): parse_json_dict(), fill_recipe_slots(), fill_recipe_slots_llm(), format_recipe_catalog(), _looks_like_agent_brief(), params_grounded(), propose_recipe_llm(), Any (+5 more)

### Community 52 - "MainTests"
Cohesion: 0.08
Nodes (5): MainTests, Tests for the cua daemon CLI helpers., RunningPidTests, ShimTests, StartStopTests

### Community 53 - "_StreamSession"
Cohesion: 0.13
Nodes (9): Any, Count spoken words for the reply delivery cutoff., _StreamSession, _tts_word_count(), DecodedMessagePrefixTests, decoded_message_prefix(), extract_message_field(), Best-effort final ``message`` from complete or nearly-complete tool JSON. (+1 more)

### Community 54 - "dictation.py"
Cohesion: 0.13
Nodes (20): cmd_start(), cmd_status(), cmd_stop(), dictation_enabled(), DictationDaemon, ensure_dictation_running(), _install_fn_tap(), _is_globe_fn_key() (+12 more)

### Community 55 - "low_latency.py"
Cohesion: 0.14
Nodes (12): Any, _engine(), PublicApiTests, patch, Unit tests for low-latency streaming TTS public API and helpers., concat_wavs(), Join WAV blobs that share the same format (streaming TTS chunks)., Print a ``[tts-latency] …`` line when TTS_LATENCY_LOG=1. (+4 more)

### Community 56 - "mcp_auth.py"
Cohesion: 0.13
Nodes (25): _dispatch_mcp(), BearerTokenAuth, build_oauth_provider(), cmd_mcp_login(), cmd_mcp_logout(), cmd_mcp_status(), format_apps_help(), format_status() (+17 more)

### Community 57 - "FileTokenStorage"
Cohesion: 0.21
Nodes (5): FileTokenStorage, logged_in_names(), Any, Path, JSON token + client-info store (chmod 600).

### Community 58 - "mcp_client.py"
Cohesion: 0.25
Nodes (11): expand_env_value(), _expand_map(), _format_call_result(), McpTool, parse_mcp_arguments(), _parse_servers(), Any, MCP client for the voice orchestrator and computer-use agent. Load servers from… (+3 more)

### Community 59 - "LiveStdioTests"
Cohesion: 0.10
Nodes (6): skipUnless, ConfigTests, ConnectErrorIsolationTests, LiveStdioTests, Tests for MCP config, read-only gating, and a live stdio echo server., ReadOnlyTests

### Community 60 - "accessibility.py"
Cohesion: 0.21
Nodes (19): accessibility_available(), _ax_frame(), _ax_get(), _ax_str(), _collect_lines(), _find_app(), focused_edit_info(), _frontmost_app() (+11 more)

### Community 61 - "observe.py"
Cohesion: 0.10
Nodes (45): accept_draft(), _append_events_log(), _archive_draft(), _capture_focused_display(), _capture_png(), _capture_png_bytes(), _capture_primary_png(), cmd_accept() (+37 more)

### Community 62 - "barge_router.py"
Cohesion: 0.12
Nodes (12): BargeDecision, classify_barge_utterance(), _extract_json(), Any, OpenAI, Classify TTS barge-in: new computer task vs answer/clarification., Result of LLM barge-in routing., Ask a cheap model whether a barge-in replaces the current work with a new task.… (+4 more)

### Community 63 - "kokoro.py"
Cohesion: 0.20
Nodes (17): _audio_from_result(), _ensure_misaki_en(), _ensure_mlx_g2p_fallback(), _float_to_wav(), _lang_code(), _load_mlx(), _load_onnx(), _pcm_to_wav() (+9 more)

### Community 64 - "piper.py"
Cohesion: 0.21
Nodes (13): PiperVoicePathTests, _ensure_voice_files(), _load(), _load_piper(), _onnx_path(), _pcm_to_wav(), Path, Piper local TTS (ONNX, CPU). ``synthesize_wav`` → WAV bytes. (+5 more)

### Community 65 - "_seed_dir"
Cohesion: 0.16
Nodes (5): TestCase, GroundingTests, Path, RecipeRunTests, _seed_dir()

### Community 66 - "active_tts_voice"
Cohesion: 0.13
Nodes (15): KokoroSynthesizeTests, LocalVoiceMappingTests, PiperSynthesizeTests, dict, patch, Local Piper / Kokoro TTS adapters., _read_wav_frames(), ActiveTtsVoiceTests (+7 more)

### Community 67 - "McpManager"
Cohesion: 0.17
Nodes (13): get_manager(), _is_fatal(), _LiveServer, load_mcp_config(), _mcp_error_text(), McpManager, BaseException, Path (+5 more)

### Community 68 - "resolve_agent_task"
Cohesion: 0.18
Nodes (10): AgentTaskSpec, is_procedure_brief(), Planner vs actor: start_task is a goal, not a UI screenplay. The orchestrator…, True when the text is a how-to screenplay instead of a user goal., What the actor should match on vs what it should optimize for., Recipes match ``match_text`` (the spoken request). The computer-use prompt uses…, resolve_agent_task(), ProcedureBriefTests (+2 more)

### Community 69 - "resolve_execution_route"
Cohesion: 0.24
Nodes (11): ExecutionRoute, _matching_recipe_name(), Deterministic fast/slow routing and specialist execution lanes. The router…, Choose a cheap first approach and the specialist prompt lane., resolve_execution_route(), test_browser_submission_uses_slow_path(), test_dense_cad_routes_to_visual_slow_path(), test_git_routes_to_terminal_fast_path() (+3 more)

### Community 70 - ".feed"
Cohesion: 0.50
Nodes (4): ndarray, Return True once when a wake phrase is detected on this stream., _resample_to_wake(), _score_from_predict()

### Community 71 - "phone_gateway.py"
Cohesion: 0.07
Nodes (46): parse_reply_sink_param(), Parse optional API ``sink`` / ``speaker``. ``None`` / empty means this request…, read_phone_screen(), read_phone_speech(), advertise_urls(), audio_to_wav(), ensure_phone_gateway(), ingest_phone_audio() (+38 more)

### Community 72 - "main.js"
Cohesion: 0.19
Nodes (16): { app, BrowserWindow, ipcMain, shell, session, systemPreferences }, applyOverlayBehavior(), BRIDGE_PORT, bridgeRequest(), CONTROL_PORT, createWindow(), fs, hideMainWindow() (+8 more)

### Community 73 - "resolve_blobatar"
Cohesion: 0.20
Nodes (6): blobatar_ids(), _normalize_seed(), resolve_blobatar(), set_blobatar(), _valid_seed(), BlobatarPresetTests

### Community 74 - "test_artifact_paths.py"
Cohesion: 0.29
Nodes (12): default_output_dir(), ensure_output_dir(), output_rule(), Path, Canonical paths for user-facing files created by the computer-use agent., Default destination unless the user explicitly names another location., Path, test_always_on_policy_includes_output_rule() (+4 more)

### Community 75 - "LiveDictationPaster"
Cohesion: 0.18
Nodes (7): _backspace_n(), LiveDictationPaster, Return matching word-prefix boundaries in two transcript snapshots. Rolling…, Paste growing STT partials; revise via AX or backspace when text changes., Sync to the final transcript and restore the clipboard., Remove anything we inserted (cancel) and restore the clipboard., _stable_prefix_boundary()

### Community 76 - "recipes.py"
Cohesion: 0.16
Nodes (22): collect_logged_commands(), _computer_action_count(), _default_templates(), _normalize_http_url(), parameterize_opened_url(), propose_recipe_from_log(), Parameterized desktop recipes: stable prefix, optional computer-use handoff. A…, Prefix https:// for bare hosts (draw.io → https://draw.io). (+14 more)

### Community 77 - "._run_one"
Cohesion: 0.14
Nodes (12): ActionStopped, _is_blocked_chord(), _mac_scroll_pixels(), normalize_key(), Exception, Post trackpad-like continuous pixel scroll events via Quartz. pyautogui's line-…, Scroll by approximate pixel deltas. dy>0 scrolls content up (wheel up)., Raised when should_stop() fires mid-batch (wake word / quit). (+4 more)

### Community 78 - "ConfigUpsertTests"
Cohesion: 0.13
Nodes (4): ConfigUpsertTests, Tests for MCP browser-login helpers (no live OAuth)., ResolveAppTests, TokenStorageTests

### Community 79 - "running_pid"
Cohesion: 0.13
Nodes (19): _cleanup_side_processes(), _clear_pid_file(), cmd_status(), cmd_stop(), find_agent_pids(), kill_agent_pids(), _pgrep_pids(), PID of a live orchestrator, if any (pid file or status.json). (+11 more)

### Community 80 - "Observer"
Cohesion: 0.21
Nodes (5): computer_use_active(), exclude_app(), Observer, True while a computer-use job owns the pointer., ObserverAutoMemoryTests

### Community 81 - "session_compact.py"
Cohesion: 0.29
Nodes (14): _clip(), compact_session_thread(), fold_task_history(), _format_tasks_for_summary(), maybe_compact_checkpoint(), Any, Orchestrator session compaction: task history folding and thread summaries., Keep the last ``TASK_HISTORY_KEEP`` tasks; summarize older ones into… (+6 more)

### Community 82 - "speaker_output.py"
Cohesion: 0.16
Nodes (10): _prompt_side_blocks(), _app_playing(), media_playing(), _osascript(), Whether media is playing on the Mac — for the computer-use agent. Reports only…, True when Music or Spotify reports player state ``playing``., One-line status for the agent, or empty when disabled., speaker_output_block() (+2 more)

### Community 83 - "test_displays.py"
Cohesion: 0.13
Nodes (7): _cg_window(), LiveLayoutMemorySkipTests, _monitor(), OccupancyFormatTests, Per-monitor window occupancy without requiring Quartz., RunningAppsAndTabsTests, WindowGeometryTests

### Community 84 - "whoami.py"
Cohesion: 0.18
Nodes (8): who_am_i reads README.md for self-description., WhoAmITests, format_whoami_output(), Path, who_am_i tool: load this project's README so the agent can describe itself., Return README markdown with HTML stripped (demo embeds, etc.)., read_project_readme(), run_whoami_tool()

### Community 85 - "timers.py"
Cohesion: 0.10
Nodes (15): Native timers: schedule, cancel, notify; speak queue is not user STT., TimerToolTests, cancel_timer(), _fire(), list_timers(), _next_id(), notify_macos(), _osa_str() (+7 more)

### Community 86 - "WakeMonitor"
Cohesion: 0.14
Nodes (6): Background wake-word listener for barge-in / idle wait. By default runs until…, Release the mic so STT (or another capture) can use it., Resume wake listening after STT (clears a stale woken flag)., Acknowledge a wake so listening can continue (persistent mode)., Block until woken (or should_stop / timeout). Assumes this monitor is already…, WakeMonitor

### Community 87 - "test_face_overlay.py"
Cohesion: 0.20
Nodes (9): face_frame_top_center(), face_overlay_enabled(), face_should_show(), True unless tray toggle / env turned the face off (default on)., Visible while the face toggle is on and not mid-screenshot hide. Does not…, Top-center of ``monitor`` in top-left desktop coordinates., FacePlacementTests, FaceVisibilityTests (+1 more)

### Community 88 - "keyboard_barge.py"
Cohesion: 0.23
Nodes (13): acquire_tts_interrupt(), _drain_stdin(), _ensure_listener_locked(), _enter_cbreak(), keyboard_barge_enabled(), _listener_loop(), Keyboard barge-in during TTS (terminal key → stop speech → listen). When the…, Return ``(event, release)`` set when any source or a barge key fires. Always… (+5 more)

### Community 89 - "test_context.py"
Cohesion: 0.15
Nodes (4): ContextBundleTests, NotToDoTests, Ephemeral context bundle (not durable memory)., TurnDesktopContextTests

### Community 91 - "TaskLog"
Cohesion: 0.17
Nodes (9): _jsonable(), Any, Path, Per-task run logging: records agent messages, tool calls, and computer actions., Compact transcript for skill-proposal and memory-extract prompts., Append-only log for a single agent run., TaskLog, MaybeCreateSkillTests (+1 more)

### Community 92 - "test_session_compact.py"
Cohesion: 0.15
Nodes (5): CheckpointTests, FoldTaskHistoryTests, FormatTaskHistoryTests, OverflowTests, Session compaction for orchestrator context limits.

### Community 93 - "ChatBridgeHandler"
Cohesion: 0.10
Nodes (15): _capture_desktop_png(), _chat_row(), ChatBridgeHandler, displays_payload(), _json_body(), _parse_display_indexes(), persist_chat_inbox(), BaseHTTPRequestHandler (+7 more)

### Community 94 - "package.json"
Cohesion: 0.17
Nodes (11): dependencies, electron, description, main, name, private, scripts, dev (+3 more)

### Community 95 - "Personal Computer Use Agent"
Cohesion: 0.17
Nodes (12): Durable memory store, Always-on computer-use policy, Isolated virtual desktop layer, HTTP-to-visible-browser escalation, Fast-path and slow-path execution router, MCP integrations, Personal Computer Use Agent, Computer-use safety and privacy controls (+4 more)

### Community 96 - "LogOverlay"
Cohesion: 0.27
Nodes (3): LogOverlay, Click-through NSPanel. Construct only on the AppKit main thread., Take the panel off screen and release it (call on tray quit).

### Community 97 - "SimpleNamespace"
Cohesion: 0.21
Nodes (5): SimpleNamespace, AssistantMessageTextTests, ChatTextOnlySpeakTests, _plain_response(), ProcessResponseActionGuardTests

### Community 99 - "format_monitor_occupancy"
Cohesion: 0.17
Nodes (13): format_monitor_occupancy(), format_running_apps(), _frontmost_name(), list_browser_tabs(), list_open_apps(), list_tabs_enabled(), parse_browser_tabs_payload(), User-facing running apps (regular activation policy), unique names. (+5 more)

### Community 100 - "speaker_id.py"
Cohesion: 0.11
Nodes (36): _accept_match(), _audio_at_embed_rate(), _best_similarity(), cosine_similarity(), embed_wav_bytes(), _get_embedder(), identify(), _identify_wav_bytes() (+28 more)

### Community 101 - "WindowBuffer"
Cohesion: 0.24
Nodes (3): Accumulates closed sessions until OBSERVE_DRAFT_SECONDS have elapsed., WindowBuffer, WindowBufferTests

### Community 103 - "app_status.py"
Cohesion: 0.05
Nodes (78): begin_tts_playback(), chat_stream_payload(), clear_logs(), clear_phone_photo(), cmd_sleep(), consume_chat_inbox(), consume_chat_inbox_items(), consume_speak() (+70 more)

### Community 104 - "webmcp_chromium.mjs"
Cohesion: 0.25
Nodes (8): command(), deadlineMs, execute(), networkResponses, pending, run(), start(), startup

### Community 106 - "list_speaker_payload"
Cohesion: 0.50
Nodes (3): list_speaker_payload(), Speaker list payload for the Electron manage-speakers page., SpeakerPayloadTests

### Community 108 - "CallbackServer"
Cohesion: 0.25
Nodes (3): AbstractEventLoop, CallbackServer, Local HTTP listener for the OAuth redirect.

### Community 109 - ".on_fn_edge"
Cohesion: 0.50
Nodes (3): Switch dots ↔ spinner without hiding. No-op if the overlay is down., set_dictation_overlay_style(), Handle Fn alone edge. Returns True if the event should be swallowed.

### Community 110 - "_listen_record_then_transcribe"
Cohesion: 0.09
Nodes (26): _dictation_provider(), _end_phrase_live_enabled(), _listen_end_hint(), listen_realtime(), _listen_record_then_transcribe(), _listen_sarvam(), _listen_whisperflow(), One-shot file transcription (OpenAI, Sarvam Saaras, or local WhisperFlow). (+18 more)

### Community 111 - "open-meteo-current-weather-report/SKILL.md"
Cohesion: 0.40
Nodes (4): simple weather_code -> text (subset), Steps, Tips, Try current_weather first (simple API form)

### Community 112 - "echo_mcp_server.py"
Cohesion: 0.32
Nodes (7): add(), delete_item(), echo(), Minimal stdio MCP server used by tests/test_mcp.py., Return the same text., Delete an item by id (write)., tool

### Community 113 - "test_harness_structure.py"
Cohesion: 0.12
Nodes (8): Live desktop snapshot attached to one orchestrator user turn., TurnDesktopContext, SessionCompactState, CheckpointTests, EventSinkTests, InputQueueTests, Harness-inspired events, queues, checkpoint, and tool runtime., ToolRuntimeTests

### Community 114 - "terminal.py"
Cohesion: 0.43
Nodes (6): _decode(), _format_report(), Run local shell commands for the computer-use agent. Captures stdout/stderr…, Execute `command` via the user's shell and return a text report. Uses the shell…, run_command(), _truncate()

### Community 115 - "try_recipe"
Cohesion: 0.18
Nodes (17): _apply_recipe_start(), handoff_prompt(), leftover_is_screenshot_only(), leftover_text(), load_recipes(), maybe_save_recipe(), _maybe_save_recipe_impl(), pick_matching_recipe() (+9 more)

### Community 116 - "current_blobatar"
Cohesion: 0.26
Nodes (12): blobatar_png_bytes(), BlobatarSpec, chat_avatar_pngs(), current_blobatar(), Any, Preset from status / runtime file / env, falling back to pebble., One selectable creature. ``extras`` are extra ovals (dx, dy, w, h) in body…, Draw the current (or given) blobatar into an ``NSImage`` for chat avatars. (+4 more)

### Community 118 - "tts_print"
Cohesion: 0.25
Nodes (10): get_client(), Shared SarvamAI client (STT + TTS)., Print a ``[tts] …`` line when TTS_LOG=1 (or ``force`` for real errors)., _speak_later_worker(), tts_print(), _pcm_to_wav(), Sarvam AI Bulbul text-to-speech (HTTP streaming → WAV)., Stream speech via Sarvam ``convert_stream`` (linear16) and return a WAV. Uses… (+2 more)

### Community 119 - "load_dotenv"
Cohesion: 0.20
Nodes (11): _dispatch_skills(), configure_native_threads(), load_dotenv(), Path, Load a local .env into os.environ (no external dependency)., Cap BLAS/OpenMP threads before numpy/OpenBLAS loads. Unbounded OpenBLAS…, Parse KEY=VALUE lines from `.env` into the process environment. By default does…, cmd_condense_skills() (+3 more)

### Community 120 - "test_stt_phone.py"
Cohesion: 0.29
Nodes (3): AskUserTests, ListenOncePhoneTests, Phone-queued text must be accepted while STT is listening (ask_user).

### Community 121 - "netflix-resume-continue-watching"
Cohesion: 0.50
Nodes (4): Netflix Continue Watching, netflix-resume-continue-watching, Most-recent media resumption, resume-paused-media-across-apps

### Community 122 - "organize-downloads-by-extension"
Cohesion: 0.33
Nodes (6): Metadata-preserving category move, move-downloads-categories-to-desktop, Safe extension-based Desktop organization, organize-desktop-by-extension, Safe extension-based Downloads organization, organize-downloads-by-extension

### Community 123 - "FaceOverlay"
Cohesion: 0.20
Nodes (5): __getattr__(), Lazily preserve ``face_overlay.FaceOverlay`` without an import cycle., FaceOverlay, Any, Animated face NSPanel. Construct only on the AppKit main thread.

### Community 124 - "run_prelude"
Cohesion: 0.29
Nodes (11): apply_params(), open_app(), open_url(), placeholders_in(), Exception, Prelude failed; caller should fall through to computer-use., RecipeError, run_prelude() (+3 more)

### Community 128 - "Email snapshot schema"
Cohesion: 0.60
Nodes (5): Email snapshot schema, gmail-extract-latest-10-emails, gmail-extract-todays-emails, Email importance heuristics, gmail-flag-today-important-and-screenshot

### Community 130 - "face_mood_for_state"
Cohesion: 0.33
Nodes (3): face_mood_for_state(), Map session phase → face mood. Prefer live TTS playback over session phase —…, FaceMoodTests

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

### Community 141 - "FanNoiseFilter"
Cohesion: 0.20
Nodes (6): _EndPhraseWatcher, FanNoiseFilter, _float_to_pcm16_b64(), ndarray, High-pass + adaptive spectral gate tuned for steady laptop/room fan noise., Live STT sidecar: stop recording when the transcript ends with the closer.

### Community 142 - "memory.py"
Cohesion: 0.07
Nodes (75): list_memories_payload(), Replace a memory file's markdown contents (full-file edit)., write_memory_payload(), apply_condensed_memory_files(), apply_extracted_memory_items(), _canonical_kind(), capture_and_save_screen(), _capture_png() (+67 more)

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

### Community 168 - "_supervise_agent"
Cohesion: 0.09
Nodes (31): phone_photo_pending(), speak_pending(), emit(), _clear_speaker_tag(), _collect_next_utterance(), _confirm_heard(), _confirm_heard_enabled(), _heard_confirm_line() (+23 more)

### Community 169 - "convert-chart-figures-to-usd/SKILL.md"
Cohesion: 0.33
Nodes (5): Read and parse lines like: Label: ₹12,000 crore  OR  Label: 12,000 (assume unit comment), Replace the line above with manual setting if you pasted rate; or instead run interactively to set `rate`., Steps, Tips, When not to use this skill

### Community 170 - "cursor-generate-project-from-prompt/SKILL.md"
Cohesion: 0.40
Nodes (4): Failure modes and recovery, Steps, Tips, When to use this skill

### Community 171 - "disable-terminal-bell-and-system-ui-sounds/SKILL.md"
Cohesion: 0.50
Nodes (3): Example quick checklist to include in your report, Steps, Tips

### Community 172 - "type_text"
Cohesion: 0.22
Nodes (10): _mac_type_paste(), _mac_type_unicode(), Paste via clipboard — fallback when Unicode injection fails in a field., Inject text into the focused control., How to inject text for computer-use ``type`` actions., Release common modifiers so the next keys go to the focused field, not…, Type via Unicode events — avoids virtual-key shortcuts (dictation, emoji…, release_stuck_modifiers() (+2 more)

### Community 187 - "status_tray_controller.py"
Cohesion: 0.12
Nodes (22): _add_memory_from_tray(), _make_template_icon(), AppKit tray controller. Imported only from status_tray.main (macOS)., _glyph_for(), _iter_orphan_tray_pids(), _latest_log_dir(), main(), Path (+14 more)

### Community 189 - "actions.py"
Cohesion: 0.17
Nodes (19): capture_all_displays_enabled(), _capture_cg_display(), capture_displays_png(), capture_monitor_image(), desktop_logical_bounds(), desktop_logical_size(), format_display_context(), list_monitors() (+11 more)

### Community 191 - "format_scheduled_tasks"
Cohesion: 0.50
Nodes (4): cmd_queue_cancel(), cmd_queue_list(), _dispatch_queue(), format_scheduled_tasks()

### Community 195 - "SmartTurnClassifier"
Cohesion: 0.13
Nodes (12): _get_smart_turn_classifier(), Return the shared local classifier, or None so transcript-idle can take over., ensure_model(), ndarray, Path, Optional local Smart Turn v3 endpoint classifier. The classifier is…, Run Smart Turn ONNX inference on mono float PCM., Return the last eight seconds as 16 kHz PCM, left-padded with silence. (+4 more)

### Community 197 - "mood_eye_pose"
Cohesion: 0.17
Nodes (8): blob_outline_points(), hsl_to_rgb(), mood_eye_pose(), H in degrees, S/L in 0–1 → RGB in 0–1., Closed pebble silhouette (polar radii, start at top)., Capsule-eye pose for a blobatar-style expression. No mouth., AppKit window and animation controller for the face overlay. The blobatar…, BlobatarStyleTests

### Community 201 - "scheduled_tasks.py"
Cohesion: 0.21
Nodes (25): _claim_due_scheduled_utterance(), Promote one due scheduled task into the normal utterance path., cancel_scheduled_task(), claim_due_task(), _clean_optional(), _ensure_dir(), _from_dict(), _iso() (+17 more)

### Community 202 - "test_recipes.py"
Cohesion: 0.36
Nodes (3): _log(), ProposeTests, Parameterized recipes: match templates, bind slots, skip unsafe URLs.

### Community 203 - "audio.py"
Cohesion: 0.08
Nodes (31): Where the next TTS line should play: Mac speakers or the phone., Whether the current turn should speak replies (vs chat text only)., Tag the current orchestrator turn (chat / voice / phone / …)., set_reply_sink(), set_reply_tts(), set_turn_source(), AudioSession, bind_audio() (+23 more)

## Knowledge Gaps
- **116 isolated node(s):** `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path`, `http`, `BRIDGE_PORT` (+111 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1292 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **50 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_status()` connect `read_status` to `face_overlay.py`, `test_chat_llm.py`, `pid_alive`, `app_status.py`, `log_overlay.py`, `wake.py`, `phone_gateway.py`, `orchestrator.py`, `running_pid`, `cua.py`, `Observer`, `observe.py`, `current_blobatar`, `dictation.py`, `test_face_overlay.py`, `chat_bridge.py`, `status_tray_controller.py`, `ChatBridgeHandler`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `LowLatencyTTS` connect `LowLatencyTTS` to `_create_response`, `audio.py`, `orchestrator.py`, `low_latency.py`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Why does `load_dotenv()` connect `load_dotenv` to `stt_race.py`, `orchestrator.py`, `skills.py`, `tts_race.py`, `agent.py`, `cua.py`, `dictation.py`, `chat_bridge.py`, `status_tray_controller.py`, `observe.py`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Are the 28 inferred relationships involving `TaskLog` (e.g. with `_extract_memories_from_log()` and `_handle_ask_user()`) actually correct?**
  _`TaskLog` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 43 inferred relationships involving `ValueError` (e.g. with `._run_one()` and `save_chat_screenshot_png()`) actually correct?**
  _`ValueError` has 43 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TrayController` (e.g. with `LogOverlay` and `main()`) actually correct?**
  _`TrayController` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path` to the rest of the system?**
  _116 weakly-connected nodes found - possible documentation gaps or missing edges._