# Computer-Use Agent Recommendations

These recommendations adapt the architecture and best practices from the [Voice AI & Voice Agents illustrated primer](https://voiceaiandvoiceagents.com/) to this repository. The project already has strong foundations—including streaming STT/TTS, wake words, barge-in, provider routing, skills, memory, context compaction, task evaluation, MCP integration, and phone input—so the focus here is on reducing latency, improving reliability and safety, and making longer computer-use tasks easier to operate and evaluate.

## Highest-priority improvements

### 1. Measure true voice-to-first-action latency

Add one end-to-end trace covering:

```text
wake detected → speech finished → transcript ready → plan ready
→ first desktop action → task complete
```

Record timings for:

- Wake detection
- STT finalization
- Orchestrator inference
- Agent startup
- Screenshot capture
- First computer action
- Each model and tool round trip
- TTS first audio
- Total task duration

Add these fields to `task_log.py`, then create a small latency report. This should reveal where the system actually feels slow rather than relying only on model- or provider-side latency.

### 2. Replace silence-only endpointing with semantic turn detection

Add a hybrid endpoint detector:

- Local VAD detects speech and non-speech.
- Partial transcripts indicate whether a sentence appears complete.
- Short silence ends complete commands quickly.
- Incomplete commands receive a longer grace period.
- The explicit “over and out” marker still ends immediately.

This should reduce the delay between the end of a command and the beginning of work without cutting off commands such as “Open Chrome and then…”.

### 3. Introduce fast-path and slow-path orchestration

Extend the existing difficulty router into two execution paths:

- **Fast path:** recipes, keyboard shortcuts, accessibility actions, terminal commands, APIs, and MCP.
- **Slow path:** screenshot-based computer use and visual reasoning.

For example, “open YouTube” should not require a complete visual-agent loop. The orchestrator should attempt deterministic execution first and fall back to vision only if verification fails.

### 4. Make function execution asynchronous

Long-running operations should not freeze the conversation. Add background tool jobs with:

- An immediate acknowledgement such as “I’m checking that now.”
- A job ID and state: queued, running, waiting, completed, or failed.
- Spoken progress only when it is useful.
- Cancellation, pausing, and redirection.
- Completion notifications through the Mac, chat, or phone.

This can build on the existing `AgentJob` implementation and allow the user to continue speaking while downloads, searches, terminal commands, or computer tasks run.

### 5. Support parallel read-only suboperations

Run independent information-gathering actions concurrently, including:

- Reading the accessibility tree while capturing a screenshot.
- Querying memory and relevant MCP services simultaneously.
- Loading a matching skill while resolving the target application.
- Running evaluator analysis while waiting for a slow UI transition.

State-changing desktop actions should remain serialized.

## Reliability improvements

### 6. Add state-aware interruption recovery

Barge-in already exists, but desktop interruption needs more precise recovery. Record:

- The last verified screen state
- Actions issued but not yet verified
- Text currently being entered
- The active tool or function call
- Whether an external side effect may have occurred

After an interruption, distinguish between:

- Stop speaking but continue working.
- Pause the task.
- Change or redirect the task.
- Undo the last reversible action.
- Answer a question without disrupting the task.

This prevents stale actions from executing after the user changes direction.

### 7. Add transactional desktop actions

Strengthen desktop action batches with explicit preconditions and postconditions:

```json
{
  "action": "click",
  "target": "Save button",
  "precondition": "Save dialog is visible",
  "postcondition": "Success banner or saved filename appears",
  "timeout": 5
}
```

If a precondition fails, stop the batch instead of clicking the same coordinates on an unexpected screen. Verify the postcondition before considering the action successful.

### 8. Introduce a proper safety policy engine

`not_to_do.md` provides prompt-level guidance, but safety should also be enforced in code. Use the tool-registry preparation phase to classify actions such as:

- Sending messages
- Submitting forms
- Making purchases
- Deleting files or cloud data
- Entering credentials or sensitive information
- Changing permissions
- Installing software
- Running generated commands

Require confirmation immediately before sensitive actions. Bind the confirmation to the exact operation, destination, and data involved.

### 9. Improve failure classification and recovery

Define explicit failure categories:

- UI target not found
- Screen changed unexpectedly
- Authentication required
- Permission missing
- Network timeout
- Model or tool failure
- Application not responding
- Repeated-action loop
- Verification failure

Give every category a bounded recovery strategy. For example, after two coordinate failures, switch to accessibility, keyboard navigation, an app-specific skill, or a user question instead of repeatedly clicking.

### 10. Build a proper computer-use evaluation suite

The existing evaluator provides periodic coaching, but the project also needs repeatable task evaluations measuring:

- Success rate
- Time to first action
- Total task duration
- Number of model turns
- Number of screenshots
- Incorrect clicks
- Recovery from interruptions
- Confirmation correctness
- Cost per completed task

Start with approximately 20 deterministic tasks across Chrome, Finder, System Settings, Maps, YouTube, and form filling. Run each task multiple times from controlled starting states.

## Context and memory improvements

### 11. Load skills progressively

Instead of placing a broad clipped catalogue into every context:

1. Retrieve the two or three most relevant skills.
2. Load only their summaries initially.
3. Load the full instructions only after selecting a skill.
4. Load reference files only when a step requires them.

This reduces prompt size and prevents irrelevant instructions from influencing the agent.

### 12. Add application-state procedural memory

Remember stable operational facts per application:

- Useful keyboard shortcuts
- Successful navigation routes
- Window-layout patterns
- Known permission limitations
- Preferred execution method: API, accessibility, keyboard, or vision
- Previously observed failure modes

This should remain separate from personal memory. It is procedural memory for operating software and should be updated only from verified outcomes.

### 13. Add task-level context compaction

Session compaction already exists, but long-running computer tasks also need their own compaction. Preserve:

- The original goal
- Completed subgoals
- Current verified UI state
- Pending work
- User corrections
- Side effects already performed
- Important values entered or retrieved

Discard old screenshots and verbose reasoning after their outcomes have been verified.

## Architectural improvements

### 14. Create specialist execution lanes

Introduce internally specialized execution lanes:

- Desktop navigator
- Browser operator
- Terminal and API operator
- Researcher
- Safety verifier
- Completion verifier

The orchestrator should choose the cheapest suitable lane. These do not initially need to be independent conversational agents; they can be specialized prompts operating over shared task state.

### 15. Add an isolated virtual desktop backend

Continue the virtual-layer work already described in `plan.md`:

- The agent does not steal the user’s mouse and keyboard.
- Tasks can continue in the background.
- Multiple tasks can run independently.
- Risky experiments are contained.
- Starting states become reproducible for evaluations.

Keep the existing controller interface and provide separate local-Mac and virtual-desktop implementations.

### 16. Complete hybrid local/cloud inference

The repository already supports local STT and TTS providers. Extend the design so that:

- Wake word, VAD, noise handling, speaker identification, simple intent routing, and privacy-sensitive transcription can run locally.
- Difficult reasoning and computer vision can run in the cloud.
- Basic commands continue to work through a local fallback when offline.
- Routing responds dynamically to latency, privacy requirements, cost, and task complexity.

### 17. Add dynamic multimodal responses

Speech is not always the best response surface. When the user asks “Where is that setting?”, the agent should be able to:

- Highlight the relevant control using the overlay.
- Number visible candidate controls.
- Display a compact confirmation card.
- Show task progress and pending actions.
- Present retrieved options for voice selection.

This can build on the existing face, status, chat, log, and dictation overlays.

## Recommended implementation order

1. End-to-end latency tracing
2. Semantic turn detection
3. Fast-path versus slow-path routing
4. Transactional actions with verification
5. Safety policy enforcement
6. Repeatable evaluation suite
7. Asynchronous background jobs
8. Task-level context compaction
9. Application procedural memory
10. Virtual desktop backend

## Guiding product metric

For this project, low-latency voice AI should mean more than fast speech generation. The primary experience metric should be:

> How quickly, safely, and visibly does the system move from spoken intent to the first useful, verified computer action?
