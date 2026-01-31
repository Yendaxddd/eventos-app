# Counter GIF and Mirror Shard Threshold Fixes

## Date: Current Session
## Status: ✅ COMPLETE - Ready for Testing

---

## Issue 1: Counter GIFs Not Displaying
**Problem:** Counter GIFs were using expired Discord URLs instead of local assets.

**Solution:** Integrated local counter GIF assets from `assets/counter_gifs/` directory.

### Changes Made:
1. **Updated counter_gif initialization** (Line ~317):
   - Changed from: `counter_gif = "expired_url"`
   - Changed to: `counter_gif_dir = pathlib.Path("assets/counter_gifs")`

2. **Added `get_random_counter_gif()` function** (Line ~3693):
   ```python
   async def get_random_counter_gif(self) -> Optional[discord.File]:
       """Load a random counter GIF from local assets directory"""
       if not self.counter_gif_dir.exists():
           log.warning("Counter GIF directory not found")
           return None
       
       gif_files = list(self.counter_gif_dir.glob("*.png")) + \
                   list(self.counter_gif_dir.glob("*.jpg")) + \
                   list(self.counter_gif_dir.glob("*.gif"))
       
       if not gif_files:
           log.warning("No counter GIF files found")
           return None
       
       chosen_file = random.choice(gif_files)
       return discord.File(chosen_file, filename=chosen_file.name)
   ```

3. **Updated counter GIF selection logic** (Line ~5407):
   - Checks for user custom GIFs first
   - Falls back to random local GIF from assets
   - Sends as `discord.File` attachment

4. **Modified embed sending** (Line ~5425):
   ```python
   await channel.send(file=counter_file, embed=embed)
   ```

### Expected Behavior:
- Counter GIFs now load from `assets/counter_gifs/` (15 PNG images)
- Random selection from available images
- Displays as attachment in counter embed
- Falls back to user custom GIFs if set via `/setcountergif`

---

## Issue 2: Mirror Shard Thresholds Not Graduated
**Problem:** All bonuses unlocked at final threshold (30 spins), making progression feel unrewarding.

**Solution:** Restructured thresholds to unlock gradually at 5, 10, 15, and 20 spins per difficulty.

### Changes Made:
Updated `data/special_objects/approved/mirror_shard.json`:

#### Old Structure (All at 30):
```json
"easy": {
    "thresholds": [5, 15, 30]
}
```

#### New Structure (Graduated):
```json
"easy": {
    "thresholds": [5],
    "effects": [
        ["damage_reduction:10"]
    ]
},
"medium": {
    "thresholds": [5, 10],
    "effects": [
        ["damage_reduction:15"],
        ["damage_reduction:30"]
    ]
},
"hard": {
    "thresholds": [5, 10, 15],
    "effects": [
        ["damage_reduction:20"],
        ["damage_reduction:30"],
        ["damage_reduction:40", "on_evade:heal_percent:10"]
    ]
},
"impossible": {
    "thresholds": [5, 10, 15, 20],
    "effects": [
        ["damage_reduction:25"],
        ["damage_reduction:35"],
        ["damage_reduction:45"],
        ["damage_reduction:50", "invoke_qte:medium", "on_stun:black_flash", "on_stun:boss_damage_percent:20"]
    ]
}
```

#### Threshold Progression Table:
| Difficulty | Spins → Effects |
|-----------|----------------|
| **Easy** | 5 → 10% reduction |
| **Medium** | 5 → 15%, 10 → 30% |
| **Hard** | 5 → 20%, 10 → 30%, 15 → 40% + 10% heal on evade |
| **Impossible** | 5 → 25%, 10 → 35%, 15 → 45%, 20 → 50% + invoke_qte + BF bonuses |

### Key Changes:
- **Max spins reduced:** 30 → 20
- **Removed conditionals array:** All effects now directly in thresholds
- **Graduated progression:** Each milestone provides incremental rewards
- **Impossible 20 finale:** invoke_qte, black_flash on stun, 20% boss damage

### Expected Behavior:
- Players see progress feedback at each threshold
- Effects stack cumulatively
- Final bonuses unlock at 20 spins (impossible difficulty)
- Better pacing for adaptation progression

---

## Testing Checklist

### Counter GIF Display:
- [ ] Use `*evade*` within 1.5s to enable counter window
- [ ] Use `*attack*` to trigger counter
- [ ] Verify GIF displays from `assets/counter_gifs/`
- [ ] Check console for any file loading errors
- [ ] Test custom GIF override with `/setcountergif`

### Mirror Shard Thresholds:
- [ ] Use `*adapt*` during counter window on easy difficulty
- [ ] Verify threshold unlocks at 5 spins
- [ ] Test medium difficulty: 5 → 10 progression
- [ ] Test hard difficulty: 5 → 10 → 15 progression
- [ ] Test impossible difficulty: 5 → 10 → 15 → 20 progression
- [ ] Verify final effects at impossible 20 (invoke_qte, black_flash)

---

## Files Modified
1. `discord-bot/advanced_qte_hp_system_debug.py` (3 replacements + 1 new function)
2. `discord-bot/data/special_objects/approved/mirror_shard.json` (complete threshold restructure)

## Dependencies
- `pathlib.Path` for asset directory handling
- `discord.File` for local file attachment
- Existing counter system (`counter_enabled_players`, `user_counter_gifs`)

## Notes
- Local assets must exist in `assets/counter_gifs/` directory
- 15 PNG images confirmed present
- No breaking changes to existing counter/adapt functionality
- Backwards compatible with user custom GIF settings

---

## Next Steps
1. **Test both fixes** with live bot
2. **Verify threshold feedback messages** display correctly
3. **Continue Skill Builder implementation** once validated:
   - `/submitattack` command
   - `/approveattack` command
   - `/rejectattack` command
   - Attack execution system
