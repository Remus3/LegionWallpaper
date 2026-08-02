# SHA rewrite map - 2026-08-01 public-release history purge

`git filter-repo --invert-paths --path style.jpg --path style2.jpg` rewrote
every commit from the first one that touched those blobs (`152d84f`,
2026-07-29) through the then-HEAD `e81eb74`. 306 commits in, 306 out - no
commit was dropped, only the two blobs and the shas downstream of them.
Commits BEFORE `152d84f` kept their shas and are still cited correctly
everywhere.

This table maps every OLD sha cited in a tracked doc (`docs/LEDGER.md`,
`docs/history_notes.md`, `WAKEUP_NOTES.md`, `docs/*.md`) that no longer
resolves, to its rewritten replacement. 43 entries. The doc text itself was
deliberately NOT edited - the ledger is append-only and the old shas are
accurate labels for what happened at the time.

The authoritative full 306-line map lived at `.git/filter-repo/commit-map`
on the operator's box and is NOT tracked (it is local git plumbing, and it
is regenerated/overwritten by any later rewrite). This table is the
durable subset - the shas anything in the repo actually references.

| old sha | new sha | subject |
|---|---|---|
| `0192010` | `375afdd` | feat(first-pass): merge the fetched-fullview glob slice |
| `0c57899` | `5099a48` | feat(rundash): the directive-history spine - run id, cost, |
| `0ee1c9e` | `faac97e` | feat(rundash): merge the verifier-verdict persistence slic |
| `14ec61f` | `ec38749` | feat(orchestrator): P4 - the file-claim table, so disjoint |
| `152d84f` | `8afab90` | feat(intake): 20 originals intaken with the recovery water |
| `1d3c2c5` | `d5810e8` | feat(rundash): join the three run-id namespaces, on eviden |
| `1eaa135` | `31e5d96` | docs(mcp-lift): P3 - the wiki has the pixels, and neither  |
| `278792e` | `751702d` | feat(hooks): P1 - the Stop-hook claimed-green gate, and th |
| `27b22c3` | `1253bab` | feat(rundash): P4 Operator Queue and P5 Suite Trajectory |
| `34634b8` | `00ae1f4` | docs(g1): merge the USM halo census slice |
| `37b9814` | `4f88831` | chore(loop): flip to N=3 and apply the three-repo slots re |
| `3cc0d92` | `f502543` | fix(gpu): one GpuBusy for every consumer, and close the tw |
| `3e8ce6a` | `61b34f4` | feat(loop): truth_gate persists what it observed onto the  |
| `4732eeb` | `77937d2` | feat(gpu): merge the GPU mutex wiring slice |
| `4c2e0d3` | `9451535` | fix(recover): the one-off diagnostic still called an incon |
| `55033cf` | `7fffd41` | test(loop): measure three-way concurrency with real proces |
| `5daa195` | `808d96b` | fix(pipeline): finalize silently dropped an operator audit |
| `621e8d1` | `a751b19` | feat(rundash): mirror the agent fleet before Claude Code r |
| `6d7efc2` | `6e1aa9b` | docs(backlog): P6 closed as NOT APPLICABLE - LW replays no |
| `71baedd` | `7fe4785` | feat(rundash): P6 Fleet History - read the mirror nothing  |
| `7879af2` | `852a721` | fix(rundash): a live clock made the time-in-status bound f |
| `8d66439` | `60dd217` | feat(anat): merge the head-spine diagnostic slice - gating |
| `94bea85` | `d737f01` | feat(pipeline): merge the approval-override recording slic |
| `95fc63b` | `fc4bf4e` | docs(roadmap): DWPose is onnx-CPU, so it is not one of the |
| `9d38fa0` | `ca5ecfd` | docs(mcp-lift): the off-list sources ARE retrievable, and  |
| `9d63303` | `879ddd6` | fix(recover): P2 - mockd replay, and the non-200 branch it |
| `9fb57c1` | `f3e34a0` | chore(orchestrator): merge the headless run-infra slice |
| `a14ab3f` | `6830211` | fix(loop): wire truth_gate into the run flow, and fix what |
| `a26e690` | `ebc970f` | docs: sync living docs - P7 shipped, LW's f1-phase6 item 7 |
| `a76a05d` | `cdc93df` | feat(gpu): wire the last three CUDA consumers - the lane i |
| `b64b92d` | `547dffd` | feat(rundash): merge the run dashboard server and page |
| `b66637f` | `ec7c17e` | feat(gpu): merge the last three CUDA consumers - no consum |
| `b7814b3` | `be057ee` | feat(orchestrator): P7 start gate - a slice cannot begin u |
| `c526c8b` | `7a20a0f` | docs(mcp-lift): close L1, kill L2's flag half, file the Gp |
| `cd2a996` | `0cd8991` | feat(rundash): P1b Cycle History panel, and the cost bound |
| `cf9dfcc` | `7927d09` | docs(mcp-lift): stage-4 deep dive - all 63 read at source, |
| `d24b494` | `bee362c` | docs(mcp-lift): P5 - memi audited our pages and got them b |
| `d460e95` | `a270dce` | feat(clean): land the confirmed per-slug presets and drain |
| `d570d42` | `5d2600e` | feat(rundash): persist verifier verdicts so the P2 chip ca |
| `ddfd50f` | `8717016` | fix(recover): merge the oEmbed-inconclusive slice |
| `e1103df` | `31e68c7` | docs(triage): LW-native MCP lift triage - 63 links, LW rub |
| `e436128` | `bf06cf6` | docs(claude): PreToolUse hooks DO fire headless on 2.1.220 |
| `e63a50d` | `eb8e442` | fix(loop): a recycled pid wedged the headless loop for fiv |
