# Graph Report - computer-use-agent  (2026-09-04)

## Corpus Check
- 224 files · ~205,485 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3437 nodes · 7531 edges · 207 communities (156 shown, 50 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 262 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `07de42f6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ValueError
- face_overlay.py
- app.js
- strip_wake_phrase
- app_status.py
- whisperflow.py
- status_tray.py
- phone_gateway.py
- overlay_should_show
- wake.py
- PhoneGatewayHttpTests
- stt/__init__.py
- skills.py
- tts_race.py
- observe.py
- agent.py
- webmcp.py
- orchestrator.py
- cua.py
- test_orchestrator_questions.py
- ChatStore
- test_harness_structure.py
- Any
- LowLatencyTTS
- MemoryStoreTests
- chat_bridge.py
- Focus
- browser_data.py
- tts/__init__.py
- AskUserBridge
- Session
- context.py
- _create_response
- llm_client.py
- chat_overlay.py
- tools_registry.py
- Path
- speaker_enroll.py
- DraftAcceptTests
- FlagTests
- dictation_overlay.py
- evaluator.py
- speaker_id.py
- PhoneTtsSinkTests
- _Response
- SpeakerIdTests
- test_actions.py
- test_wake.py
- latency_report.py
- TurnTrace
- memory_graph.py
- try_recipe
- MainTests
- low_latency.py
- dictation.py
- test_face_overlay.py
- mcp_auth.py
- FileTokenStorage
- utterance_match.py
- LiveStdioTests
- accessibility.py
- Any
- barge_router.py
- WebMCPTests
- task_feedback.py
- _seed_dir
- active_tts_voice
- mcp_client.py
- resolve_agent_task
- events.py
- current_blobatar
- piper.py
- main.js
- Recipe
- test_artifact_paths.py
- LiveDictationPaster
- recipes.py
- checkpoint.py
- ConfigUpsertTests
- resolve_execution_route
- Observer
- McpManager
- speaker_output.py
- .feed
- whoami.py
- timers.py
- WakeMonitor
- audio.py
- keyboard_barge.py
- test_context.py
- FnFlagTests
- .record
- test_session_compact.py
- ._run_one
- package.json
- Personal Computer Use Agent
- ensure_inbox_worker
- ChatScreenshotTurnTests
- SimpleNamespace
- test_displays.py
- BrowserDataTests
- WindowBuffer
- fill_recipe_slots_llm
- ._run_session
- webmcp_chromium.mjs
- ChatStreamTests
- kokoro.py
- ToolRegistryTests
- CallbackServer
- DictationDaemon
- listen_once
- score_speakers
- echo_mcp_server.py
- check-weather-and-report-rain/SKILL.md
- terminal.py
- read_status
- tts_print
- OverlayFrameTests
- session_compact.py
- load_dotenv
- test_stt_phone.py
- netflix-resume-continue-watching
- organize-downloads-by-extension
- FaceOverlay
- choose_transcript
- displays.py
- LlmClientTests
- BearerTokenAuth
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
- _MarkdownParser
- type_text
- convert-chart-figures-to-usd/SKILL.md
- cursor-generate-project-from-prompt/SKILL.md
- disable-terminal-bell-and-system-ui-sounds/SKILL.md
- face_overlay_enabled
- test_recipes.py
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
- _FakeResponsesClient
- trigger_listen_shortcut
- open-diagrams-from-folder/SKILL.md
- actions.py
- MatchTemplateTests
- UrlSafetyTests
- save-and-preview-svg/SKILL.md
- upwork-evaluate-and-apply/SKILL.md
- upwork-update-profile-from-resume/SKILL.md
- SmartTurnClassifier
- FacePayloadTests
- mood_eye_pose
- LogOverlay
- build_system_prompt
- _exit_on_signal
- _ListenHotkeys
- _read
- transcribe
- ComputerUseGateTests
- ParseExtractTests
- OrchestratorCommandTests

## God Nodes (most connected - your core abstractions)
1. `run_orchestrator()` - 63 edges
2. `read_status()` - 50 edges
3. `run()` - 48 edges
4. `_read()` - 45 edges
5. `TaskLog` - 45 edges
6. `_write()` - 36 edges
7. `LowLatencyTTS` - 33 edges
8. `_supervise_agent()` - 31 edges
9. `wire()` - 29 edges
10. `ChatStore` - 29 edges

## Surprising Connections (you probably didn't know these)
- `_handle_ask_user()` --calls--> `is_mark_done_utterance()`  [INFERRED]
  agent.py → status_control.py
- `_handle_read_skill()` --uses--> `TaskLog`  [INFERRED]
  agent.py → task_log.py
- `run()` --calls--> `consume_mark_done()`  [INFERRED]
  agent.py → status_control.py
- `run()` --calls--> `register_agent_process()`  [INFERRED]
  agent.py → status_control.py
- `run()` --calls--> `remove_agent()`  [INFERRED]
  agent.py → status_control.py

## Import Cycles
- None detected.

## Communities (207 total, 50 thin omitted)

### Community 0 - "ValueError"
Cohesion: 0.16
Nodes (31): Replace a memory file's markdown contents (full-file edit)., write_memory_payload(), apply_condensed_memory_files(), apply_extracted_memory_items(), _canonical_kind(), capture_and_save_screen(), ensure_memory_dirs(), list_memories() (+23 more)

### Community 1 - "face_overlay.py"
Cohesion: 0.28
Nodes (15): _extras_circle(), _feed(), _finalize(), _hashed_blobatar(), _i32(), _imul(), _int(), _jitter() (+7 more)

### Community 2 - "app.js"
Cohesion: 0.06
Nodes (83): acceptDrafts(), applyCustomFace(), applyDisplaysPayload(), applyFaceStatus(), applyObserveStatus(), autosize(), boot(), bufferToBase64() (+75 more)

### Community 3 - "strip_wake_phrase"
Cohesion: 0.14
Nodes (16): _strip_listen_wake(), matches_wake_phrase(), normalize_speech_text(), _parse_wake_phrases(), _phrases_to_check(), Comma-separated wake phrases; longest-first friendly, case-preserving., True if `text` contains any configured wake phrase (TTS echo guard)., True if transcript starts with (or equals) any configured wake phrase. (+8 more)

### Community 4 - "app_status.py"
Cohesion: 0.07
Nodes (65): _encode_phone_jpeg(), publish_phone_screen(), Shared live status + recent log lines for the macOS menu-bar tray. Orchestrator…, Synchronously encode the agent's PNG and replace ``phone-screen.jpg``., Share the latest computer-use screenshot with the phone gateway., write_phone_screen(), ModuleType, apply_control() (+57 more)

### Community 5 - "whisperflow.py"
Cohesion: 0.06
Nodes (47): _load_wav(), _log(), main(), _openai_model(), _provider_ready(), Path, race_once(), RaceResult (+39 more)

### Community 6 - "status_tray.py"
Cohesion: 0.13
Nodes (25): ack_overlay_hidden(), Show or hide the top-center face panel (tray menu toggle)., When True, wake word is ignored (Sleep)., Flip Sleep mode; returns True when Sleep is now on., Tray confirms the panel is actually off-screen (or back)., set_face_overlay_enabled(), set_tray_pid(), sleep_mode_enabled() (+17 more)

### Community 7 - "phone_gateway.py"
Cohesion: 0.07
Nodes (45): parse_reply_sink_param(), Parse optional API ``sink`` / ``speaker``. ``None`` / empty means this request…, read_phone_screen(), read_phone_speech(), advertise_urls(), audio_to_wav(), ensure_phone_gateway(), ingest_phone_audio() (+37 more)

### Community 8 - "overlay_should_show"
Cohesion: 0.12
Nodes (17): format_overlay_text(), overlay_enabled(), overlay_frame_top_left(), overlay_owner_alive(), overlay_should_show(), overlay_target_monitor(), Any, True unless the tray toggle turned the panel off (default on). (+9 more)

### Community 9 - "wake.py"
Cohesion: 0.08
Nodes (44): _default_end_model_spec(), _default_phrase_for_models(), _default_wake_model(), _download_file(), _ensure_model(), format_end_listen_phrases(), format_listen_end_hint(), _format_phrase_list() (+36 more)

### Community 10 - "PhoneGatewayHttpTests"
Cohesion: 0.05
Nodes (8): AdvertiseUrlsTests, EnsureGatewayTests, PhoneAudioIngestTests, PhoneGatewayEnabledTests, PhoneGatewayHttpTests, PhoneGatewayTokenTests, PhonePhotoIngestTests, Phone gateway: env switch, auth, command queue (no live network bind required).

### Community 11 - "stt/__init__.py"
Cohesion: 0.09
Nodes (48): _cancel_pending(), _cancel_requested(), _capture_sample_rate(), _emit_partial(), _event_delta(), _event_transcript(), _event_type(), _float_to_wav() (+40 more)

### Community 12 - "skills.py"
Cohesion: 0.10
Nodes (46): _handle_read_skill(), cmd_condense_skills(), _condense_one_skill(), condense_skills(), delete_skill_folder(), discover_skills(), format_skill_catalog(), _format_skills_for_merge() (+38 more)

### Community 13 - "tts_race.py"
Cohesion: 0.20
Nodes (22): _mlx_available(), Synthesize ``text`` with Kokoro and return WAV bytes., synthesize_wav(), _kokoro_voice(), _log(), main(), _openai_voice(), _piper_voice() (+14 more)

### Community 14 - "observe.py"
Cohesion: 0.15
Nodes (22): _capture_cg_display(), _capture_focused_display(), _capture_png(), _capture_png_bytes(), _capture_primary_png(), cmd_start(), cmd_status(), cmd_stop() (+14 more)

### Community 15 - "agent.py"
Cohesion: 0.08
Nodes (48): DesktopController, Wraps pyautogui with coordinate remapping between screenshot space and actual…, _action_summary(), confirm(), _confirm_terminal(), _extract_json_object(), _extract_memories_from_log(), _handle_ask_user() (+40 more)

### Community 16 - "webmcp.py"
Cohesion: 0.21
Nodes (16): _bridge(), _BridgeSession, call_webmcp_tool(), list_webmcp_tools(), _node_binary(), _persistent_bridge(), Any, RuntimeError (+8 more)

### Community 17 - "orchestrator.py"
Cohesion: 0.06
Nodes (77): chat_text_only(), log_llm(), phone_photo_pending(), Put an LLM reply in the status log (and ``last_llm``) for the phone / tray., Chat turn with speaker off — reply in the UI, not via TTS or status blurbs., reply_sink(), reply_tts_enabled(), set_last_spoken() (+69 more)

### Community 18 - "cua.py"
Cohesion: 0.09
Nodes (43): cmd_sleep(), ``cua sleep`` / ``on`` / ``off`` / ``toggle``., _cleanup_side_processes(), _clear_pid_file(), cmd_help(), cmd_install(), cmd_start(), cmd_status() (+35 more)

### Community 19 - "test_orchestrator_questions.py"
Cohesion: 0.08
Nodes (18): _confirm_heard_enabled(), _give_response_closes_turn(), _looks_like_question(), Build Responses API ``input`` for one user turn (optional phone + desktop…, True when spoken text expects a reply (so we must open the mic)., Drop trailing 'I'll wait / I'm ready' padding from a spoken reply., True if give_response_to_user spoke after `start_index` (this response only)., True when a statement was spoken and the model must not talk again. (+10 more)

### Community 20 - "ChatStore"
Cohesion: 0.07
Nodes (17): ChatRow, ChatStore, _connect(), _init_schema(), MessageRow, Path, Local SQLite chat history + screenshot files for the desktop chat UI., Thread-safe SQLite store for chats / messages / prefs. (+9 more)

### Community 21 - "test_harness_structure.py"
Cohesion: 0.12
Nodes (8): Live desktop snapshot attached to one orchestrator user turn., TurnDesktopContext, SessionCompactState, CheckpointTests, EventSinkTests, InputQueueTests, Harness-inspired events, queues, checkpoint, and tool runtime., ToolRuntimeTests

### Community 22 - "Any"
Cohesion: 0.20
Nodes (21): _as_mapping(), assign_windows_to_monitors(), _cg_window_list(), frontmost_window_info(), _keep_window(), list_windows_by_monitor(), monitor_containing_point(), monitor_for_app_window() (+13 more)

### Community 23 - "LowLatencyTTS"
Cohesion: 0.09
Nodes (15): LowLatencyTTS, OpenAI, Path, Thread-safe two-stage (synthesis → playback) streaming TTS pipeline., Reuse the process-wide persistent wake monitor (never stop it here)., Wake and/or keyboard interrupt event + release callback., Stop remaining synthesis/playback after a wake-word barge-in., Begin a streaming TTS session for ``response_id`` (public API). (+7 more)

### Community 24 - "MemoryStoreTests"
Cohesion: 0.05
Nodes (5): CondenseMemoryTests, ExtractMemoryTests, MemoryStoreTests, Tests for personal / app memory storage., TurnTraceTests

### Community 25 - "chat_bridge.py"
Cohesion: 0.09
Nodes (47): Write a chat-attached PNG for the orchestrator; return basename for enqueue., save_chat_screenshot_png(), accept_observe_draft(), _capture_desktop_png(), _chat_row(), ChatBridgeHandler, command_for_orchestrator(), delete_mcp_connection() (+39 more)

### Community 26 - "Focus"
Cohesion: 0.11
Nodes (7): Focus, SessionBuffer, ExcludeAppTests, FocusedDisplayCaptureTests, ObserverFlushTests, Tests for the passive observer (session flush, drafts, accept)., SessionBufferTests

### Community 27 - "browser_data.py"
Cohesion: 0.15
Nodes (29): _apply_operation(), BrowserDataError, _chromium_binary(), _decode(), discover_endpoints(), _discovery_terms(), _endpoint_score(), fetch_chromium() (+21 more)

### Community 28 - "tts/__init__.py"
Cohesion: 0.12
Nodes (29): Publish a Mac-synthesized WAV for the phone to play locally., write_phone_speech(), _apply_fade(), _numpy(), _phone_reply_sink(), _play_afplay(), _play_sounddevice(), play_wav() (+21 more)

### Community 29 - "AskUserBridge"
Cohesion: 0.08
Nodes (17): AgentMessageInbox, AskUserBridge, extract_jarvis_command(), ZeroMQ message bus: orchestrator → computer agent (while agent is running).…, Drain typed messages into steer / follow_up / next_run buckets., Blocking ask_user from the agent worker thread to the orchestrator main thread.…, Called from the agent worker thread. Blocks until orchestrator replies., True if the agent has queued an ask_user the orchestrator hasn't taken yet. (+9 more)

### Community 30 - "Session"
Cohesion: 0.08
Nodes (19): Update high-level status shown in the menu bar., Set state and append the same message to the log ring., set_and_log(), set_state(), bind_session(), _canon(), _project(), Any (+11 more)

### Community 31 - "context.py"
Cohesion: 0.20
Nodes (15): assemble_context(), _capture_desktop_context(), capture_turn_desktop_context(), _clip(), ContextBundle, _orchestrator_desktop_ax_enabled(), orchestrator_desktop_enabled(), _orchestrator_desktop_screenshot_enabled() (+7 more)

### Community 32 - "_create_response"
Cohesion: 0.12
Nodes (21): True when this turn was queued from the Electron chat app., reply_to_chat(), turn_source(), _create_response(), _exception_blob(), is_fatal_llm_error(), llm_error_speech(), LlmUnavailableError (+13 more)

### Community 33 - "llm_client.py"
Cohesion: 0.12
Nodes (28): _continue_response(), Follow-up Responses turn. DeepSeek must replay function_call items (stateless)., agent_provider(), fold_orphan_tool_outputs(), function_call_input_items(), input_has_image(), _item_call_id(), _item_output_text() (+20 more)

### Community 34 - "chat_overlay.py"
Cohesion: 0.09
Nodes (30): ensure_chat_bridge(), Popen, Start the bridge subprocess if not already running., chat_overlay_enabled(), chat_overlay_env_enabled(), chat_should_show(), cmd_chat(), command_for_orchestrator() (+22 more)

### Community 35 - "tools_registry.py"
Cohesion: 0.12
Nodes (33): Brain, Any, Explicit screen read for the read_screen tool — display layout, AX text, and…, Follow-up user message so the model sees the read_screen PNG., read_screen(), read_screen_vision_input(), mcp_openai_tools(), agent_tools() (+25 more)

### Community 36 - "Path"
Cohesion: 0.14
Nodes (9): CondenseParseTests, CondenseRunTests, CuaSkillsCommandTests, DiscoverSkillsTests, MergeParseTests, MergeRunTests, Path, Tests for skill discovery and cua skills condense. (+1 more)

### Community 37 - "speaker_enroll.py"
Cohesion: 0.18
Nodes (23): enroll_speaker_from_body(), cmd_delete(), cmd_enroll(), cmd_list(), cmd_test(), main(), OpenAI, Interactive speaker enrollment: read five passages (three long, two short),… (+15 more)

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
Cohesion: 0.16
Nodes (29): _audio_at_embed_rate(), _best_similarity(), cosine_similarity(), embed_wav_bytes(), enroll_speaker(), _get_embedder(), load_profile(), _pairwise_min() (+21 more)

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
Cohesion: 0.19
Nodes (21): _append_trace(), build_report(), _durations(), finish_trace(), _fmt_ms(), _percentile(), Any, Path (+13 more)

### Community 49 - "TurnTrace"
Cohesion: 0.16
Nodes (17): User utterance plus each LLM step (replies, tool calls, results)., TurnTrace, _completed_task_match(), _completed_tasks_in_turn(), _normalized_task_goal(), Stable form for rejecting accidental post-completion relaunches., Return a completed near-duplicate from this orchestrator session., Pair start_task/result trace steps from only the current user turn. (+9 more)

### Community 50 - "memory_graph.py"
Cohesion: 0.16
Nodes (26): datetime, apply_observation_graph(), _claim_id(), _clean_entity(), compact_graph(), _connect(), database_path(), export_graphify() (+18 more)

### Community 51 - "try_recipe"
Cohesion: 0.18
Nodes (17): format_recipe_catalog(), leftover_is_screenshot_only(), load_recipes(), maybe_save_recipe(), _maybe_save_recipe_impl(), pick_matching_recipe(), propose_recipe_llm(), Any (+9 more)

### Community 52 - "MainTests"
Cohesion: 0.09
Nodes (5): MainTests, Tests for the cua daemon CLI helpers., RunningPidTests, ShimTests, StartStopTests

### Community 53 - "low_latency.py"
Cohesion: 0.12
Nodes (17): Any, DecodedMessagePrefixTests, _engine(), PublicApiTests, patch, Unit tests for low-latency streaming TTS public API and helpers., concat_wavs(), Join WAV blobs that share the same format (streaming TTS chunks). (+9 more)

### Community 54 - "dictation.py"
Cohesion: 0.18
Nodes (17): cmd_start(), cmd_status(), cmd_stop(), dictation_enabled(), ensure_dictation_running(), _is_globe_fn_key(), _keystroke_v(), paste_dictation() (+9 more)

### Community 55 - "test_face_overlay.py"
Cohesion: 0.15
Nodes (10): blobatar_ids(), face_frame_top_center(), _normalize_seed(), Top-center of ``monitor`` in top-left desktop coordinates., resolve_blobatar(), set_blobatar(), _valid_seed(), BlobatarPresetTests (+2 more)

### Community 56 - "mcp_auth.py"
Cohesion: 0.21
Nodes (20): build_oauth_provider(), cmd_mcp_login(), cmd_mcp_logout(), format_apps_help(), _gh_bin(), _gh_login_browser(), _gh_token(), is_dcr_failure() (+12 more)

### Community 57 - "FileTokenStorage"
Cohesion: 0.17
Nodes (8): FileTokenStorage, format_status(), logged_in_names(), oauth_httpx_auth(), Any, Path, httpx Auth for a connected HTTP MCP server, or None., JSON token + client-info store (chmod 600).

### Community 58 - "utterance_match.py"
Cohesion: 0.33
Nodes (9): _bind_without_template(), parameterize_opened_url(), Replace task-specific bits in an opened URL with placeholders., content_words(), _extract_urls(), match_phrases_for(), _norm(), _phrase_in() (+1 more)

### Community 59 - "LiveStdioTests"
Cohesion: 0.10
Nodes (6): skipUnless, ConfigTests, ConnectErrorIsolationTests, LiveStdioTests, Tests for MCP config, read-only gating, and a live stdio echo server., ReadOnlyTests

### Community 60 - "accessibility.py"
Cohesion: 0.21
Nodes (19): accessibility_available(), _ax_frame(), _ax_get(), _ax_str(), _collect_lines(), _find_app(), focused_edit_info(), _frontmost_app() (+11 more)

### Community 61 - "Any"
Cohesion: 0.16
Nodes (25): accept_draft(), _append_events_log(), _archive_draft(), cmd_accept(), cmd_list(), cmd_reject(), compact_observe_artifacts(), _find_drafts() (+17 more)

### Community 62 - "barge_router.py"
Cohesion: 0.12
Nodes (12): BargeDecision, classify_barge_utterance(), _extract_json(), Any, OpenAI, Classify TTS barge-in: new computer task vs answer/clarification., Result of LLM barge-in routing., Ask a cheap model whether a barge-in replaces the current work with a new task.… (+4 more)

### Community 63 - "WebMCPTests"
Cohesion: 0.25
Nodes (3): discovery(), WebMCP discovery, validation, and mutation-boundary tests., WebMCPTests

### Community 64 - "task_feedback.py"
Cohesion: 0.17
Nodes (19): collect_post_task_feedback(), feedback_enabled(), format_feedback_for_model(), interpret_feedback_text(), load_task_actions(), Any, OpenAI, Post-task user feedback: spoken prompt, persisted with goal and action log. (+11 more)

### Community 65 - "_seed_dir"
Cohesion: 0.16
Nodes (5): TestCase, GroundingTests, Path, RecipeRunTests, _seed_dir()

### Community 66 - "active_tts_voice"
Cohesion: 0.15
Nodes (14): LocalVoiceMappingTests, PiperSynthesizeTests, dict, patch, Local Piper / Kokoro TTS adapters., _read_wav_frames(), ActiveTtsVoiceTests, patch (+6 more)

### Community 67 - "mcp_client.py"
Cohesion: 0.20
Nodes (14): expand_env_value(), _expand_map(), _format_call_result(), load_mcp_config(), McpTool, parse_mcp_arguments(), _parse_servers(), Any (+6 more)

### Community 68 - "resolve_agent_task"
Cohesion: 0.16
Nodes (11): _looks_like_agent_brief(), AgentTaskSpec, is_procedure_brief(), Planner vs actor: start_task is a goal, not a UI screenplay. The orchestrator…, True when the text is a how-to screenplay instead of a user goal., What the actor should match on vs what it should optimize for., Recipes match ``match_text`` (the spoken request). The computer-use prompt uses…, resolve_agent_task() (+3 more)

### Community 69 - "events.py"
Cohesion: 0.14
Nodes (14): bind_events(), _default_logger(), Event, EventSink, get_events(), Any, BaseException, Typed event sink for the orchestrator and computer agent. Events observe… (+6 more)

### Community 70 - "current_blobatar"
Cohesion: 0.23
Nodes (13): blobatar_png_bytes(), BlobatarSpec, chat_avatar_pngs(), current_blobatar(), format_blobatar_list(), Any, Preset from status / runtime file / env, falling back to pebble., One selectable creature. ``extras`` are extra ovals (dx, dy, w, h) in body… (+5 more)

### Community 71 - "piper.py"
Cohesion: 0.21
Nodes (13): PiperVoicePathTests, _ensure_voice_files(), _load(), _load_piper(), _onnx_path(), _pcm_to_wav(), Path, Piper local TTS (ONNX, CPU). ``synthesize_wav`` → WAV bytes. (+5 more)

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
Cohesion: 0.18
Nodes (7): _backspace_n(), LiveDictationPaster, Return matching word-prefix boundaries in two transcript snapshots. Rolling…, Paste growing STT partials; revise via AX or backspace when text changes., Sync to the final transcript and restore the clipboard., Remove anything we inserted (cancel) and restore the clipboard., _stable_prefix_boundary()

### Community 76 - "recipes.py"
Cohesion: 0.16
Nodes (24): apply_params(), collect_logged_commands(), _computer_action_count(), _default_templates(), leftover_text(), _normalize_http_url(), open_app(), open_url() (+16 more)

### Community 77 - "checkpoint.py"
Cohesion: 0.17
Nodes (12): CheckpointResult, Any, Orchestrator turn checkpoint (harness-v2 §4). Between turns the lane passes a…, Run one orchestrator checkpoint before (or after recovering) a model call.…, run_orchestrator_checkpoint(), bind_next_run_queue(), get_next_run_queue(), NextRunQueue (+4 more)

### Community 78 - "ConfigUpsertTests"
Cohesion: 0.13
Nodes (4): ConfigUpsertTests, Tests for MCP browser-login helpers (no live OAuth)., ResolveAppTests, TokenStorageTests

### Community 79 - "resolve_execution_route"
Cohesion: 0.24
Nodes (11): ExecutionRoute, _matching_recipe_name(), Deterministic fast/slow routing and specialist execution lanes. The router…, Choose a cheap first approach and the specialist prompt lane., resolve_execution_route(), test_browser_submission_uses_slow_path(), test_dense_cad_routes_to_visual_slow_path(), test_git_routes_to_terminal_fast_path() (+3 more)

### Community 80 - "Observer"
Cohesion: 0.21
Nodes (5): computer_use_active(), exclude_app(), Observer, True while a computer-use job owns the pointer., ObserverAutoMemoryTests

### Community 81 - "McpManager"
Cohesion: 0.22
Nodes (10): get_manager(), _is_fatal(), _LiveServer, _mcp_error_text(), McpManager, BaseException, Long-lived MCP sessions on a background asyncio loop., Connect (or reconnect) a configured server. Returns an error string or None. (+2 more)

### Community 82 - "speaker_output.py"
Cohesion: 0.18
Nodes (9): _app_playing(), media_playing(), _osascript(), Whether media is playing on the Mac — for the computer-use agent. Reports only…, True when Music or Spotify reports player state ``playing``., One-line status for the agent, or empty when disabled., speaker_output_block(), Media playing yes/no for the agent (no AppleScript in tests). (+1 more)

### Community 83 - ".feed"
Cohesion: 0.50
Nodes (4): ndarray, Return True once when a wake phrase is detected on this stream., _resample_to_wake(), _score_from_predict()

### Community 84 - "whoami.py"
Cohesion: 0.18
Nodes (8): who_am_i reads README.md for self-description., WhoAmITests, format_whoami_output(), Path, who_am_i tool: load this project's README so the agent can describe itself., Return README markdown with HTML stripped (demo embeds, etc.)., read_project_readme(), run_whoami_tool()

### Community 85 - "timers.py"
Cohesion: 0.10
Nodes (15): Native timers: schedule, cancel, notify; speak queue is not user STT., TimerToolTests, cancel_timer(), _fire(), list_timers(), _next_id(), notify_macos(), _osa_str() (+7 more)

### Community 86 - "WakeMonitor"
Cohesion: 0.14
Nodes (6): Background wake-word listener for barge-in / idle wait. By default runs until…, Release the mic so STT (or another capture) can use it., Resume wake listening after STT (clears a stale woken flag)., Acknowledge a wake so listening can continue (persistent mode)., Block until woken (or should_stop / timeout). Assumes this monitor is already…, WakeMonitor

### Community 87 - "audio.py"
Cohesion: 0.08
Nodes (29): speak_pending(), utterance_pending(), AudioSession, bind_audio(), OpenAI, Session, Single owner for wake, STT, TTS, and barge-in. The capture implementations stay…, Wake word → one cloud STT utterance. Returns None if stopped or empty. (+21 more)

### Community 88 - "keyboard_barge.py"
Cohesion: 0.23
Nodes (13): acquire_tts_interrupt(), _drain_stdin(), _ensure_listener_locked(), _enter_cbreak(), keyboard_barge_enabled(), _listener_loop(), Keyboard barge-in during TTS (terminal key → stop speech → listen). When the…, Return ``(event, release)`` set when any source or a barge key fires. Always… (+5 more)

### Community 89 - "test_context.py"
Cohesion: 0.15
Nodes (4): ContextBundleTests, NotToDoTests, Ephemeral context bundle (not durable memory)., TurnDesktopContextTests

### Community 91 - ".record"
Cohesion: 0.32
Nodes (3): _jsonable(), Any, Path

### Community 92 - "test_session_compact.py"
Cohesion: 0.15
Nodes (5): CheckpointTests, FoldTaskHistoryTests, FormatTaskHistoryTests, OverflowTests, Session compaction for orchestrator context limits.

### Community 93 - "._run_one"
Cohesion: 0.13
Nodes (13): ActionStopped, _is_blocked_chord(), _mac_scroll_pixels(), normalize_key(), Exception, Post trackpad-like continuous pixel scroll events via Quartz. pyautogui's line-…, Scroll by approximate pixel deltas. dy>0 scrolls content up (wheel up)., Raised when should_stop() fires mid-batch (wake word / quit). (+5 more)

### Community 94 - "package.json"
Cohesion: 0.17
Nodes (11): dependencies, electron, description, main, name, private, scripts, dev (+3 more)

### Community 95 - "Personal Computer Use Agent"
Cohesion: 0.17
Nodes (12): Durable memory store, Always-on computer-use policy, Isolated virtual desktop layer, HTTP-to-visible-browser escalation, Fast-path and slow-path execution router, MCP integrations, Personal Computer Use Agent, Computer-use safety and privacy controls (+4 more)

### Community 96 - "ensure_inbox_worker"
Cohesion: 0.29
Nodes (6): ensure_inbox_worker(), load_or_create_token(), main(), _new_token(), Background drain so persistence does not depend on UI polling., serve_forever()

### Community 98 - "SimpleNamespace"
Cohesion: 0.21
Nodes (4): SimpleNamespace, AssistantMessageTextTests, ChatTextOnlySpeakTests, KokoroSynthesizeTests

### Community 99 - "test_displays.py"
Cohesion: 0.13
Nodes (7): _cg_window(), LiveLayoutMemorySkipTests, _monitor(), OccupancyFormatTests, Per-monitor window occupancy without requiring Quartz., RunningAppsAndTabsTests, WindowGeometryTests

### Community 101 - "WindowBuffer"
Cohesion: 0.24
Nodes (3): Accumulates closed sessions until OBSERVE_DRAFT_SECONDS have elapsed., WindowBuffer, WindowBufferTests

### Community 102 - "fill_recipe_slots_llm"
Cohesion: 0.24
Nodes (10): _extract_json_object(), fill_recipe_slots(), fill_recipe_slots_llm(), params_grounded(), True when the slot is actually present in this request (not a prior place)., Short remainder after a URL open — never 'create a new tab / navigate'., Fill {{placeholders}}. Regex first; EVAL_MODEL only if bind fails., _recipe_slot_names() (+2 more)

### Community 103 - "._run_session"
Cohesion: 0.18
Nodes (11): _cue_listen_start(), Ping as soon as the STT stream is open — do not block capture., _afplay(), pause_persistent_wake(), play_listen_end_chime(), play_listen_start_chime(), play_wake_chime(), Play a macOS system sound. Returns True if afplay was started. (+3 more)

### Community 104 - "webmcp_chromium.mjs"
Cohesion: 0.25
Nodes (8): command(), deadlineMs, execute(), networkResponses, pending, run(), start(), startup

### Community 106 - "kokoro.py"
Cohesion: 0.20
Nodes (17): _audio_from_result(), _ensure_misaki_en(), _ensure_mlx_g2p_fallback(), _float_to_wav(), _lang_code(), _load_mlx(), _load_onnx(), _pcm_to_wav() (+9 more)

### Community 108 - "CallbackServer"
Cohesion: 0.25
Nodes (3): AbstractEventLoop, CallbackServer, Local HTTP listener for the OAuth redirect.

### Community 109 - "DictationDaemon"
Cohesion: 0.20
Nodes (7): DictationDaemon, _install_fn_tap(), main(), Switch dots ↔ spinner without hiding. No-op if the overlay is down., set_dictation_overlay_style(), Handle Fn alone edge. Returns True if the event should be swallowed., run_dictation()

### Community 110 - "listen_once"
Cohesion: 0.10
Nodes (27): enabled(), set_last_speaker(), _consume_phone_utterance(), _end_phrase_live_enabled(), listen_and_confirm(), _listen_end_hint(), _listen_end_spotter(), listen_for_utterance() (+19 more)

### Community 111 - "score_speakers"
Cohesion: 0.24
Nodes (9): _accept_match(), identify(), _identify_wav_bytes(), Score ``wav_bytes`` against every enrolled profile (best score first)., Match ``wav_bytes`` to an enrolled speaker, or None if unknown., Identify without logging; returns (match or None, ranked scores)., score_speakers(), ScoredSpeaker (+1 more)

### Community 112 - "echo_mcp_server.py"
Cohesion: 0.32
Nodes (7): add(), delete_item(), echo(), Minimal stdio MCP server used by tests/test_mcp.py., Return the same text., Delete an item by id (write)., tool

### Community 114 - "terminal.py"
Cohesion: 0.43
Nodes (6): _decode(), _format_report(), Run local shell commands for the computer-use agent. Captures stdout/stderr…, Execute `command` via the user's shell and return a text report. Uses the shell…, run_command(), _truncate()

### Community 115 - "read_status"
Cohesion: 0.13
Nodes (14): Snapshot for the tray (or callers)., Ask the tray overlay to hide (True) or show (False) for a screenshot., read_status(), set_overlay_hidden(), chat_bridge_enabled(), Bridge runs when chat is on, or CHAT_BRIDGE=1 forces it., pause_overlay_for_capture(), _post_overlay_note() (+6 more)

### Community 116 - "tts_print"
Cohesion: 0.29
Nodes (9): get_client(), Shared SarvamAI client (STT + TTS)., Print a ``[tts] …`` line when TTS_LOG=1 (or ``force`` for real errors)., tts_print(), _pcm_to_wav(), Sarvam AI Bulbul text-to-speech (HTTP streaming → WAV)., Stream speech via Sarvam ``convert_stream`` (linear16) and return a WAV. Uses…, _split_text() (+1 more)

### Community 118 - "session_compact.py"
Cohesion: 0.28
Nodes (15): _clip(), compact_session_thread(), _extract_response_text(), fold_task_history(), _format_tasks_for_summary(), maybe_compact_checkpoint(), Any, Orchestrator session compaction: task history folding and thread summaries. (+7 more)

### Community 119 - "load_dotenv"
Cohesion: 0.25
Nodes (8): configure_native_threads(), load_dotenv(), Path, Load a local .env into os.environ (no external dependency)., Cap BLAS/OpenMP threads before numpy/OpenBLAS loads. Unbounded OpenBLAS…, Parse KEY=VALUE lines from `.env` into the process environment. By default does…, cmd_merge_skills(), CLI entry for ``cua skills merge``. Loads ``.env`` and calls the model.

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

### Community 124 - "choose_transcript"
Cohesion: 0.25
Nodes (8): choose_transcript(), classify_yes_no(), _normalize_reply(), Pick the more relevant / coherent of live vs refined transcripts., Re-transcribe the committed clip with REFINE_MODEL and choose vs live. Returns…, Return 'yes', 'no', 'quit', 'retry', or None if unclear., refine_after_pause(), _response_output_text()

### Community 125 - "displays.py"
Cohesion: 0.19
Nodes (16): _clip_url(), format_browser_tabs(), format_monitor_occupancy(), format_running_apps(), _frontmost_name(), list_browser_tabs(), list_open_apps(), list_tabs_enabled() (+8 more)

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
Cohesion: 0.08
Nodes (49): list_memories_payload(), _capture_png(), capture_screen_png(), _condense_memories_impl(), _condense_worker(), _dated_heading_count(), _describe_screenshot(), _extract_run_memories_impl() (+41 more)

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

### Community 168 - "type_text"
Cohesion: 0.22
Nodes (10): _mac_type_paste(), _mac_type_unicode(), Paste via clipboard — fallback when Unicode injection fails in a field., Inject text into the focused control., How to inject text for computer-use ``type`` actions., Release common modifiers so the next keys go to the focused field, not…, Type via Unicode events — avoids virtual-key shortcuts (dictation, emoji…, release_stuck_modifiers() (+2 more)

### Community 169 - "convert-chart-figures-to-usd/SKILL.md"
Cohesion: 0.33
Nodes (5): Read and parse lines like: Label: ₹12,000 crore  OR  Label: 12,000 (assume unit comment), Replace the line above with manual setting if you pasted rate; or instead run interactively to set `rate`., Steps, Tips, When not to use this skill

### Community 170 - "cursor-generate-project-from-prompt/SKILL.md"
Cohesion: 0.40
Nodes (4): Failure modes and recovery, Steps, Tips, When to use this skill

### Community 171 - "disable-terminal-bell-and-system-ui-sounds/SKILL.md"
Cohesion: 0.50
Nodes (3): Example quick checklist to include in your report, Steps, Tips

### Community 172 - "face_overlay_enabled"
Cohesion: 0.32
Nodes (5): face_overlay_enabled(), face_should_show(), True unless tray toggle / env turned the face off (default on)., Visible while the face toggle is on and not mid-screenshot hide. Does not…, FaceVisibilityTests

### Community 173 - "test_recipes.py"
Cohesion: 0.36
Nodes (3): _log(), ProposeTests, Parameterized recipes: match templates, bind slots, skip unsafe URLs.

### Community 187 - "trigger_listen_shortcut"
Cohesion: 0.39
Nodes (7): Start from idle; otherwise cancel and discard the current voice turn., trigger_listen_shortcut(), Global tray shortcut behavior without loading AppKit., test_listen_shortcut_cancels_active_capture(), test_listen_shortcut_cancels_ask_user_capture(), test_listen_shortcut_cancels_turn_while_thinking(), test_listen_shortcut_starts_when_idle()

### Community 189 - "actions.py"
Cohesion: 0.14
Nodes (22): capture_all_displays_enabled(), _capture_cg_display(), capture_displays_png(), capture_monitor_image(), desktop_logical_bounds(), desktop_logical_size(), format_display_context(), list_monitors() (+14 more)

### Community 195 - "SmartTurnClassifier"
Cohesion: 0.13
Nodes (12): _get_smart_turn_classifier(), Return the shared local classifier, or None so transcript-idle can take over., ensure_model(), ndarray, Path, Optional local Smart Turn v3 endpoint classifier. The classifier is…, Run Smart Turn ONNX inference on mono float PCM., Return the last eight seconds as 16 kHz PCM, left-padded with silence. (+4 more)

### Community 197 - "mood_eye_pose"
Cohesion: 0.17
Nodes (8): blob_outline_points(), hsl_to_rgb(), mood_eye_pose(), H in degrees, S/L in 0–1 → RGB in 0–1., Closed pebble silhouette (polar radii, start at top)., Capsule-eye pose for a blobatar-style expression. No mouth., AppKit window and animation controller for the face overlay. The blobatar…, BlobatarStyleTests

### Community 198 - "LogOverlay"
Cohesion: 0.31
Nodes (3): LogOverlay, Click-through NSPanel. Construct only on the AppKit main thread., Take the panel off screen and release it (call on tray quit).

### Community 199 - "build_system_prompt"
Cohesion: 0.17
Nodes (10): _format_task_history(), _history_note(), build_system_prompt(), local_datetime_line(), Orchestrator system prompt (extracted from the turn loop)., One-line clock context injected on every orchestrator user turn., Assemble the orchestrator system prompt for one turn., format_task_history_block() (+2 more)

### Community 200 - "_exit_on_signal"
Cohesion: 0.50
Nodes (4): _exit_on_signal(), Leave signal context immediately; normal ``finally`` cleanup does the work., Signal shutdown must not acquire status locks or perform nested cleanup., test_signal_handler_only_requests_stack_unwind()

### Community 201 - "_ListenHotkeys"
Cohesion: 0.33
Nodes (3): _ListenHotkeys, TTY hotkeys while STT owns the mic: cancel (Esc) and optional send (Enter)., _stdin_is_tty()

### Community 203 - "_read"
Cohesion: 0.06
Nodes (58): begin_tts_playback(), chat_stream_payload(), clear_logs(), clear_phone_photo(), consume_chat_inbox(), consume_chat_inbox_items(), consume_speak(), consume_utterance() (+50 more)

### Community 204 - "transcribe"
Cohesion: 0.13
Nodes (15): _dictation_provider(), One-shot file transcription (OpenAI, Sarvam Saaras, or local WhisperFlow)., Providers that record a clip, then run file STT (no live partials)., Which STT backend Fn dictation uses., transcribe(), _use_file_stt(), _use_sarvam(), _use_whisperflow() (+7 more)

## Knowledge Gaps
- **111 isolated node(s):** `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path`, `http`, `BRIDGE_PORT` (+106 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1240 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **50 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_status()` connect `read_status` to `face_overlay.py`, `app_status.py`, `status_tray.py`, `phone_gateway.py`, `overlay_should_show`, `wake.py`, `observe.py`, `orchestrator.py`, `cua.py`, `chat_bridge.py`, `chat_overlay.py`, `face_overlay_enabled`, `dictation.py`, `trigger_listen_shortcut`, `current_blobatar`, `_read`, `Observer`, `._run_session`, `DictationDaemon`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `load_dotenv()` connect `load_dotenv` to `ValueError`, `whisperflow.py`, `status_tray.py`, `skills.py`, `DictationDaemon`, `observe.py`, `agent.py`, `tts_race.py`, `orchestrator.py`, `cua.py`, `dictation.py`, `chat_bridge.py`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `LowLatencyTTS` connect `LowLatencyTTS` to `_create_response`, `orchestrator.py`, `low_latency.py`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `run_orchestrator()` (e.g. with `_exit_on_signal()` and `active_agents()`) actually correct?**
  _`run_orchestrator()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `run()` (e.g. with `RecipeHit` and `consume_mark_done()`) actually correct?**
  _`run()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `TaskLog` (e.g. with `_extract_memories_from_log()` and `_handle_ask_user()`) actually correct?**
  _`TaskLog` has 26 INFERRED edges - model-reasoned connections that need verification._
- **What connects `{ app, BrowserWindow, ipcMain, shell, session, systemPreferences }`, `fs`, `path` to the rest of the system?**
  _111 weakly-connected nodes found - possible documentation gaps or missing edges._