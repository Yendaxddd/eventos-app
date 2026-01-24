# 🧪 HP SYSTEM TESTING GUIDE

## Pre-Test Setup

### 1. Environment Configuration
Ensure your `.env` file has:
```env
DISCORD_TOKEN=your_bot_token_here
QTE_CHANNEL_ID=your_channel_id
QTE_PLAYER_ROLE_ID=your_role_id
HP_BAR_THREAD_ID=your_thread_id  # ⚠️ REQUIRED FOR HP SYSTEM
```

### 2. Create HP Bar Thread
1. Go to your QTE channel in Discord
2. Right-click → Create Thread
3. Name it "⚔️ HP Bars" or similar
4. Right-click thread → Copy ID
5. Add to `.env` as `HP_BAR_THREAD_ID`

---

## 🔬 Test Scenarios

### ✅ Test 1: HP Initialization
**Expected Behavior**: Player gets 100 HP on first QTE participation

**Steps**:
1. Start bot: `python advanced_qte_hp_system_debug.py`
2. Trigger a QTE: Press `F9` (Easy Single)
3. Player responds with `*evade*` or `*parry*`
4. Check HP thread for new embed

**Success Criteria**:
- ✅ Green HP bar appears in thread
- ✅ Shows "💚 [PlayerName]"
- ✅ Displays "100/100 HP (100.0%)"
- ✅ Status: "⚔️ Fighting"

**Console Output Should Show**:
```
[green]💚 Initialized HP for user [user_id][/green]
[cyan]📊 Created new HP bar for [PlayerName][/cyan]
```

---

### ✅ Test 2: HP Damage on Failure
**Expected Behavior**: Failed QTE reduces HP by 20

**Steps**:
1. Trigger QTE: Press `F9`
2. Wait for timeout OR respond too slowly
3. Check HP bar update

**Success Criteria**:
- ✅ HP drops to 80/100
- ✅ Bar color stays green (>60%)
- ✅ Player receives damage message
- ✅ HP bar embed updates (not creates new)

**Console Output Should Show**:
```
[red]💔 User [user_id] took 20 damage! HP: 80/100[/red]
[cyan]📊 Updated HP bar for [PlayerName][/cyan]
```

---

### ✅ Test 3: HP Color Transitions
**Expected Behavior**: Bar changes color at thresholds

**Test Each Threshold**:
- **100-61 HP** → 💚 Green
- **60-31 HP** → 💛 Yellow  
- **30-1 HP** → ❤️ Red

**Steps**:
1. Fail multiple QTEs to reduce HP
2. Watch color change at each threshold

**Success Criteria**:
- ✅ Green at 80 HP (1 fail)
- ✅ Yellow at 60 HP (2 fails)
- ✅ Yellow at 40 HP (3 fails)
- ✅ Red at 20 HP (4 fails)

---

### ✅ Test 4: Death Sequence
**Expected Behavior**: At 0 HP, dramatic death sequence

**Steps**:
1. Fail 5 QTEs (100 → 0 HP)
2. Observe sequence timing

**Success Criteria**:
- ✅ Message 1: 🕊️ (dove emoji)
- ✅ *Wait 1 second*
- ✅ Message 2: "*[PlayerName] has fallen in combat...*"
- ✅ *Wait 3 seconds*
- ✅ Message 3: "@Player — Speak your final words..."
- ✅ HP bar shows: "💀 Defeated"
- ✅ Status: "💀 Defeated"

**Console Output Should Show**:
```
┌───────────────────────────────┐
│ 💀 [PlayerName] has DIED      │
└───────────────────────────────┘
```

---

### ✅ Test 5: Multiple Players
**Expected Behavior**: Each player has independent HP

**Steps**:
1. Trigger Group QTE: Press `Shift+F9`
2. Multiple players respond
3. Check HP thread

**Success Criteria**:
- ✅ Each player has separate HP bar embed
- ✅ Bars update independently
- ✅ No confusion between players

---

### ✅ Test 6: HP Persistence
**Expected Behavior**: HP persists across QTEs

**Steps**:
1. Player takes damage (80 HP)
2. Successfully completes next QTE
3. Check HP - should still be 80

**Success Criteria**:
- ✅ HP doesn't reset on success
- ✅ HP only decreases on failures
- ✅ HP tracked across multiple QTEs

---

### ✅ Test 7: Dead Player Cannot Participate
**Expected Behavior**: Dead players shouldn't be targeted

**Steps**:
1. Kill a player (0 HP)
2. Trigger more QTEs
3. Check if dead player gets targeted

**Current Status**: ⚠️ **NOT YET IMPLEMENTED**
- Dead players currently CAN be targeted
- Needs filter in `trigger_single_qte()` and `trigger_group_qte()`

---

## 🔍 Known Issues to Verify

### Issue 1: Thread Not Found
**Symptom**: Console shows "❌ HP bar thread not found!"
**Fix**: Verify `HP_BAR_THREAD_ID` in `.env` is correct

### Issue 2: Multiple HP Bars Per Player
**Symptom**: Player gets multiple HP bar messages
**Expected**: Should edit existing message, not create new
**Check**: Message history limit (currently 50)

### Issue 3: HP Bars Don't Update
**Symptom**: HP bar stays at 100 despite damage
**Possible Cause**: Display name mismatch
**Debug**: Check console for "Debug: Edited HP bar embed" messages

---

## 📊 Expected Console Output (Example Session)

```
✓ Configuration loaded
  Channel ID: 123456789
  Role ID: 987654321

✓ Loaded 5 character registrations
✓ Loaded stats for 3 players

┌──────────────────────────────────┐
│       QTE BOT ONLINE             │
│ ✓ Bot logged in as QTEBot#1234   │
│ ✓ QTE System Ready!              │
└──────────────────────────────────┘

⌨ Hotkey Bindings
┌────────┬────────┬────────┬────────┬────────────┐
│ Type   │ Easy   │ Medium │ Hard   │ Impossible │
├────────┼────────┼────────┼────────┼────────────┤
│ Single │ F9     │ F10    │ F11    │ F12        │
│ Group  │ Shift+ │ Shift+ │ Shift+ │ Shift+F12  │
│        │ F9     │ F10    │ F11    │            │
└────────┴────────┴────────┴────────┴────────────┘

[PRESS F9 TO TEST]

┌────────────────────────────────┐
│ ⚡ SINGLE QTE TRIGGERED        │
│ ID: 0                          │
│ Difficulty: EASY               │
│ Target: TestPlayer             │
└────────────────────────────────┘

[green]💚 Initialized HP for user 123456789[/green]
[cyan]📊 Created new HP bar for TestPlayer[/cyan]
[green]✓ EVADE SUCCESS - TestPlayer in 2.34s[/green]

[PRESS F9 AGAIN - LET IT TIMEOUT]

[red]✗ Single QTE TIMEOUT - TestPlayer failed[/red]
[red]💔 User 123456789 took 20 damage! HP: 80/100[/red]
[cyan]📊 Updated HP bar for TestPlayer[/cyan]
```

---

## 🎯 Success Checklist

Before moving to Phase 1 implementation:

- [ ] HP initializes at 100 for new players
- [ ] HP bars appear in dedicated thread
- [ ] HP reduces by 20 on each failure
- [ ] Colors transition (Green → Yellow → Red)
- [ ] Death sequence triggers at 0 HP
- [ ] Multiple players tracked independently
- [ ] HP persists across QTEs
- [ ] Console debug messages clear
- [ ] No duplicate HP bars created
- [ ] HP bar updates (edits) existing messages

---

## 🐛 Debugging Tips

### If HP bars don't appear:
```python
# Check console for these messages:
"⚠️ HP_BAR_THREAD_ID not set in .env file"
"❌ HP bar thread not found! Check HP_BAR_THREAD_ID"
```

### If damage doesn't apply:
```python
# Look for red damage messages:
"💔 User [id] took 20 damage! HP: X/100"
```

### If death sequence doesn't trigger:
```python
# Should see this panel:
"┌─────────────────────────────────┐"
"│ 💀 [PlayerName] has DIED        │"
"└─────────────────────────────────┘"
```

### Enable extra debugging:
Add to console.print statements if needed:
```python
console.print(f"[blue]Debug: HP data = {self.player_hp}[/blue]")
```

---

## ⚠️ Important Notes

1. **Thread must exist before bot starts** - Create it first!
2. **Players need QTE role** - Verify role assignment
3. **Tupperbox users** - Make sure characters are registered
4. **Console is your friend** - Watch for errors in real-time
5. **Test one thing at a time** - Isolate issues systematically

---

**After testing completes, document results and we'll analyze gameplay balance! 🎮**