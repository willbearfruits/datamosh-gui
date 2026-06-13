# Roadmap

Product direction for Datamosh GUI (timeline-first, experimental mosh workflow).

## Phase 1: Media Compatibility and Import Reliability

### 1. Example Media Suite
- Build a test pack covering formats/codecs/resolutions/fps:
  - Containers: MP4, MOV, MKV, AVI, WebM
  - Codecs: H.264, H.265, ProRes, DNxHD, VP9, Xvid
  - Resolutions: 480p, 720p, 1080p, 4K, portrait/mobile formats
  - Frame rates: 24, 25, 30, 50, 60, VFR edge cases
- Add automated import + normalize validation tests against this suite.
- Define expected pass/fail behavior and fallback messaging.

### 2. Import Strategy UI (Audit + Upgrade)
> **Status: shipped in v1.1.1** — import options dialog with normalize-all vs. direct-AVI modes, preset/custom controls (width/height/GOP/qscale/audio), and a persistent import profile. Remaining work below is refinement only.

- Audit current import path (auto-normalize to Xvid) and verify edge-case behavior.
- Add an import options dialog before ingest:
  - Keep original if compatible
  - Normalize fast/balanced/sharp
  - Custom width/height/GOP/qscale/audio handling
- Persist import profile defaults and allow per-clip override.
- Show clear ingest status/errors per clip.

Definition of done:
- Any supported source can be imported with deterministic behavior.
- Users can choose ingest behavior explicitly instead of hidden defaults.

## Phase 2: Advanced Timeline

### 3. Layered Timeline
- Multiple video tracks (V1, V2, V3...) with proper z-order compositing.
- Clip controls: opacity, blend mode, mute/solo/lock track.
- First blend-mode target set: Normal, Add, Screen, Multiply, Difference.

### 4. Timeline Usability Upgrades (Suggested)
- Snap to playhead/cuts with toggle.
- Ripple insert/delete modes.
- Group/ungroup segments.
- Markers and labeled regions.
- Per-track and per-clip bypass toggles for A/B checks.

Definition of done:
- Cross-layer composition is predictable in preview and final render.
- Editing operations remain stable with undo/redo.

## Phase 3: UI Polish and Workflow Speed

### 5. Toolbar Refresh
> **Status: shipped** — the toolbar is now icon-only (`ToolButtonIconOnly`) with tooltips and keyboard accelerators. Remaining work is a custom scalable icon set.

- Replace text actions with icon-first toolbar + tooltips.
- Keep keyboard shortcuts primary; toolbar as visual accelerator.
- Add scalable icon set for light/dark readability.

### 6. Optional Performance Pass
- Proxy preview mode for heavy clips.
- Pre-render cache invalidation rules for timeline edits.
- Background decode/analysis prioritization for active viewport.

## Near-Term Priority Order
1. **Project persistence** — save/load `.dmosh` project files (timeline arrangement + per-clip settings + cuts + injected I-frames). Foundational: today all work is lost on close.
2. Example media suite + ingest reliability tests
3. Layered timeline foundation
4. Opacity/blend modes
5. Custom scalable icon set for the toolbar

### Already shipped
- Import strategy dialog and persistent import profiles (v1.1.1)
- Icon-first toolbar with tooltips and accelerators
