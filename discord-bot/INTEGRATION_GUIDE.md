# NLP Action Detection System + Web Dashboard Integration Guide

## 📋 Overview

This guide provides step-by-step instructions for integrating the NLP Action Detection System and Web Dashboard with your existing QTE bot (`advanced_qte_hp_system_debug.py`).

**Version:** 3.0.0  
**Target Device:** ROG ALLY Z1 Extreme  
**Python Version:** 3.13  

---

## 🚀 Quick Start

### Step 1: Fix Python PATH

Run the PATH fix batch file to ensure Python scripts are accessible:

```bash
fix_path.bat
```

**Important:** Restart your terminal after running this script.

### Step 2: Install Dependencies

Install the required NLP and dashboard packages:

```bash
pip install -r requirements_nlp.txt
```

Download spaCy language models:

```bash
python -m spacy download en_core_web_sm
python -m spacy download es_core_news_sm
```

### Step 3: Verify Installation

Test the NLP detector:

```bash
python nlp_detector.py
```

This will run a benchmark and interactive testing session.

---

## 🔧 Integration Steps

### 1. Import NLP Detector

Add the following import at the top of `advanced_qte_hp_system_debug.py` (around line 25):

```python
from nlp_detector import ActionDetector
```

### 2. Initialize NLP Detector

In the `QTEBot.__init__()` method (around line 60), add:

```python
# Initialize NLP detector
try:
    self.nlp_detector = ActionDetector(config_path="config.json")
    console.print("[green]✓ NLP detector initialized[/green]")
except Exception as e:
    console.print(f"[yellow]⚠ NLP detector failed to initialize: {e}[/yellow]")
    self.nlp_detector = None

# NLP statistics
self.nlp_stats = {
    "detections": 0,
    "avg_time": 0.0,
    "accuracy": 0.0
}
```

### 3. Add NLP Detection to Message Handler

In the message handler (around line 316, before or after the exact command checks), add:

```python
# Natural Language Action Detection
# Only process if not an exact command (starting with *)
if not message.content.startswith('*') and self.nlp_detector:
    import time
    start_time = time.time()
    
    detected_action, confidence = self.nlp_detector.detect(message.content)
    detection_time = (time.time() - start_time) * 1000  # Convert to ms
    
    if detected_action and confidence >= 0.6:
        console.print(
            f"[cyan]🤖 NLP Detection: '{detected_action}' "
            f"(confidence: {confidence:.2f}, time: {detection_time:.2f}ms)[/cyan]"
        )
        
        # Update statistics
        self.nlp_stats["detections"] += 1
        total_time = self.nlp_stats["avg_time"] * (self.nlp_stats["detections"] - 1)
        self.nlp_stats["avg_time"] = (total_time + detection_time) / self.nlp_stats["detections"]
        
        # Route to appropriate handler based on detected action
        if detected_action == "evade":
            await self.handle_evade(message, message.author.id)
        elif detected_action == "parry":
            await self.handle_parry(message, message.author.id)
        elif detected_action == "attack":
            await self.handle_attack(message, message.author.id)
        elif detected_action == "save":
            await self.handle_save(message, message.author.id)
        elif detected_action == "heal":
            await self.handle_heal(message, message.author.id)
        elif detected_action == "power1":
            await self.handle_power1(message, message.author.id)
        elif detected_action == "power2":
            await self.handle_power2(message, message.author.id)
        
        return  # Exit after handling NLP action
```

### 4. Initialize Dashboard

Add the dashboard import at the top of the file:

```python
from dashboard.app import init_dashboard
```

In the `on_ready()` event (around line 280), add:

```python
@bot.event
async def on_ready():
    console.print(f"[green]✓ Bot logged in as {bot.user}[/green]")
    
    # Store start time for uptime calculation
    bot.start_time = time.time()
    
    # Initialize dashboard in a separate thread
    try:
        dashboard_thread = init_dashboard(
            bot,
            host='127.0.0.1',
            port=5000,
            auto_open=False  # Set to True to auto-open browser
        )
        console.print("[green]✓ Dashboard started at http://127.0.0.1:5000[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ Dashboard failed to start: {e}[/yellow]")
```

### 5. Add Helper Methods (Optional)

Add these helper methods to your `QTEBot` class for better integration:

```python
def get_nlp_stats(self):
    """Get NLP detection statistics."""
    if self.nlp_detector:
        return self.nlp_detector.get_stats()
    return {}

def add_nlp_pattern(self, action: str, pattern: str, pattern_type: str = "regex"):
    """Dynamically add a new NLP pattern."""
    if self.nlp_detector:
        return self.nlp_detector.add_pattern(action, pattern, pattern_type)
    return False
```

---

## 📝 Configuration

Edit `config.json` to customize behavior:

### NLP Settings

```json
{
  "nlp": {
    "enabled": true,
    "confidence_threshold": 0.6,  // Minimum confidence to accept detection
    "max_cache_size": 1000,       // Cache size for patterns
    "enable_language_detection": true,
    "performance_mode": "balanced" // fast, balanced, or accurate
  }
}
```

### Dashboard Settings

```json
{
  "dashboard": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 5000,
    "auto_open": false,           // Auto-open browser on start
    "update_interval": 2000       // Update interval in ms
  }
}
```

---

## 🧪 Testing

### Test NLP Detection

1. **Start the bot** with the integrated code
2. **Send test messages** in Discord:
   - "I dodge!" → Should detect as `evade`
   - "¡esquivo!" → Should detect as `evade`
   - "attacking back" → Should detect as `attack`
   - "I'll heal" → Should detect as `heal`
   - "block that" → Should detect as `parry`

3. **Check console output** for NLP detection logs

### Test Dashboard

1. **Open browser** and navigate to: `http://127.0.0.1:5000`
2. **Verify connection status** shows "Connected" (green dot)
3. **Test NLP detection** in the dashboard's NLP monitor
4. **Trigger QTE** using dashboard buttons
5. **Add changelog entry** using the + button
6. **Check real-time updates** - HP bars should update automatically

---

## 🎯 Usage Examples

### Basic NLP Detection

```python
# The bot will automatically detect natural language commands
# User sends: "I'm going to dodge this attack"
# Bot detects: action='evade', confidence=0.85
```

### Custom Pattern Addition

```python
# Add a custom exact match pattern
bot.add_nlp_pattern("evade", "duck", "exact")

# Add a custom regex pattern
bot.add_nlp_pattern("attack", r'\b(strike|hit)\s+hard\b', "regex")
```

### Dashboard Integration

The dashboard automatically connects to the bot and provides:
- **Real-time HP monitoring** with animated bars
- **Live NLP statistics** showing detection performance
- **Quick action buttons** for testing QTEs
- **Changelog management** with search and filter
- **Performance metrics** (CPU, memory, uptime)

---

## 🔍 Troubleshooting

### Issue: NLP Not Detecting

**Solutions:**
1. Check confidence threshold in `config.json`
2. Verify spaCy models are installed:
   ```bash
   python -m spacy validate
   ```
3. Test detector independently:
   ```bash
   python nlp_detector.py
   ```

### Issue: Dashboard Not Loading

**Solutions:**
1. Check if port 5000 is available:
   ```bash
   netstat -an | findstr :5000
   ```
2. Try a different port in `config.json`
3. Check firewall settings
4. Verify Flask is installed:
   ```bash
   pip show flask
   ```

### Issue: Slow Detection Times

**Solutions:**
1. Change `performance_mode` to `"fast"` in `config.json`
2. Reduce `max_cache_size`
3. Disable language detection if not needed
4. Use lightweight spaCy models (already default)

### Issue: High Memory Usage

**Solutions:**
1. Reduce `max_cache_size` in config
2. Disable NLP if not needed: `"enabled": false`
3. Close unused browser tabs with dashboard

---

## 📊 Performance Expectations (ROG ALLY Z1 Extreme)

### NLP Detection
- **Average detection time:** < 10ms
- **Accuracy:** > 90%
- **Memory usage:** ~150-200MB
- **CPU impact:** Minimal (< 5%)

### Dashboard
- **Memory usage:** ~50MB
- **CPU impact:** Minimal (< 2%)
- **Network:** Local only (no internet required)

### Combined System
- **Total memory:** ~250MB additional
- **CPU impact:** < 10% during active use
- **Startup time:** +2-3 seconds

---

## 🎮 ROG ALLY Optimization Tips

1. **Use Performance Mode** for gaming sessions
2. **Close dashboard** if not needed (saves resources)
3. **Adjust NLP threshold** based on accuracy needs
4. **Monitor performance** in dashboard metrics
5. **Use exact commands** for fastest response (`*evade`, `*attack`)

---

## 🔄 Changelog System

### Adding Entries via Code

```python
from changelog_manager import ChangelogManager

changelog = ChangelogManager()
changelog.add_change(
    title="New Feature",
    description="Added awesome functionality",
    category="feature",
    files_changed=["file1.py"],
    impact="high"
)
```

### Adding Entries via Dashboard

1. Click **"+ Add"** button in changelog panel
2. Fill in title and description
3. Select category and impact level
4. Add files changed (optional)
5. Click **"Add Entry"**

### Exporting Changelog

```python
changelog.export_markdown("CHANGELOG.md")
changelog.export_html("changelog.html")
```

---

## 📚 API Reference

### ActionDetector Methods

```python
# Detect action from text
action, confidence = detector.detect("I dodge!")

# Add custom pattern
detector.add_pattern("evade", "duck", "exact")

# Get statistics
stats = detector.get_stats()

# Reset statistics
detector.reset_stats()

# Clear cache
detector.clear_cache()
```

### Dashboard API Endpoints

- `GET /api/status` - Get bot status
- `GET /api/changelog` - Get changelog entries
- `POST /api/trigger_qte` - Trigger QTE event
- `POST /api/adjust` - Adjust bot parameters
- `POST /api/changelog/add` - Add changelog entry
- `GET /api/stats/nlp` - Get NLP statistics

---

## 🐛 Known Issues

1. **Language detection sometimes incorrect** - Set specific language if needed
2. **Dashboard may lag with 100+ changelog entries** - Use filters
3. **First NLP detection slower** - Models load on first use

---

## 🔮 Future Enhancements

- [ ] Multi-user NLP customization
- [ ] Advanced pattern learning
- [ ] Voice command support
- [ ] Mobile dashboard view
- [ ] Cloud sync for changelog
- [ ] Performance profiling tools

---

## 📞 Support

For issues or questions:
1. Check this guide's troubleshooting section
2. Review `qte_bot.log` for errors
3. Test components independently
4. Check `config.json` settings

---

## 📄 License

Part of the QTE Bot system - Version 3.0.0

---

## ✅ Integration Checklist

- [ ] Installed dependencies (`pip install -r requirements_nlp.txt`)
- [ ] Downloaded spaCy models
- [ ] Added NLP detector imports
- [ ] Initialized NLP detector in bot
- [ ] Added NLP detection to message handler
- [ ] Added dashboard initialization
- [ ] Configured `config.json`
- [ ] Tested NLP detection
- [ ] Tested dashboard access
- [ ] Verified real-time updates
- [ ] Added changelog entries

**When all items are checked, your integration is complete! 🎉**