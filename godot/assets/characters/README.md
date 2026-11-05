# Character asset slots

The client supports optional imported rigged GLB characters. Add licensed or original files with these exact paths:

- `owner.glb`
- `reception.glb`
- `secretary.glb`
- `lead.glb`
- `coo.glb`
- `architect.glb`
- `frontend.glb`
- `qa.glb`
- `backend.glb`
- `api.glb`

The GLB root must import as a `Node3D` scene and should contain an `AnimationPlayer`. When a matching file is absent, the procedural fallback is used automatically. No third-party character assets are bundled in this release.

## Animation clip aliases

The client looks for the first available clip from each alias group:

| State | Clip candidates |
|---|---|
| Idle | `Idle`, `idle`, `Standing` |
| Walk | `Walk`, `Walking`, `walk` |
| Work | `Type`, `Typing`, `Sitting_Computer` |
| Speak | `Talk`, `Talking`, `Conversation` |
| Listen | `Listen`, `Listening`, `Idle_Seated` |
| Write / read | `Write`, `Writing`, `Reading` |
| Phone | `Phone`, `TalkingOnPhone`, `Call` |

Keep the model at a human scale of approximately 1.65–1.85 m, facing local `-Z`, with feet near the origin. Ensure the animation clips loop appropriately. Record source, creator, license, attribution and modification in `docs/ASSET-REGISTER.md` before committing any external asset.
