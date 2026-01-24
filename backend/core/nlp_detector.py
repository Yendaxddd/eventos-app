"""
NLP Action Detection System
Optimized for ROG ALLY Z1 Extreme
Author: Kilo Code
Version: 3.0.0
"""

import re
import time
import json
from typing import Tuple, Optional, Dict, List
from collections import defaultdict
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ActionDetector:
    """
    High-performance NLP action detection with multi-language support.
    Detection flow: Creative Moves -> Exact Match → Regex Patterns → spaCy NLP
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the action detector with optional configuration."""
        self.config = self._load_config(config_path)
        
        # Performance tracking
        self.stats = {
            "total_detections": 0,
            "exact_matches": 0,
            "regex_matches": 0,
            "nlp_matches": 0,
            "avg_detection_time": 0.0,
            "total_time": 0.0,
            "accuracy_score": 0.0
        }
        
        # Cache for frequent patterns
        self.pattern_cache = {}
        self.max_cache_size = self.config.get("max_cache_size", 1000)
        
        # Action types supported
        self.action_types = ["evade", "parry", "attack", "save", "heal", "power1", "power2"]
        
        # Initialize detection layers
        self._init_creative_moves()
        self._init_exact_commands()
        self._init_regex_patterns()
        self._init_nlp_models()
    
    def _init_creative_moves(self):
        """Load creative moves from JSON file."""
        self.creative_moves = {}
        try:
            with open('eventos-app/backend/data/creative_moves.json', 'r', encoding='utf-8') as f:
                self.creative_moves = json.load(f)
            logger.info(f"Loaded {len(self.creative_moves)} creative moves")
        except Exception as e:
            logger.warning(f"Could not load creative_moves.json: {e}")
        
        logger.info("ActionDetector initialized successfully")
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from file or use defaults."""
        default_config = {
            "confidence_threshold": 0.6,
            "max_cache_size": 1000,
            "enable_language_detection": True,
            "enable_nlp": True,
            "performance_mode": "balanced"  # fast, balanced, accurate
        }
        
        if config_path:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    return {**default_config, **config_data.get("nlp", {})}
            except Exception as e:
                logger.warning(f"Could not load config: {e}. Using defaults.")
        
        return default_config
    
    def _init_exact_commands(self):
        """Initialize exact command matching (fastest layer)."""
        self.exact_commands = {
            # English commands
            "evade": ["evade", "dodge", "avoid", "sidestep", "duck"],
            "parry": ["parry", "block", "deflect", "counter"],
            "attack": ["attack", "strike", "hit", "slash", "punch", "kick"],
            "save": ["save", "rescue", "protect", "guard"],
            "heal": ["heal", "restore", "cure", "mend", "recover"],
            "power1": ["power1", "special1", "ability1", "skill1"],
            "power2": ["power2", "special2", "ability2", "skill2"],
            
            # Spanish commands
            "esquivar": ["evade"],
            "esquivo": ["evade"],
            "parar": ["parry"],
            "bloquear": ["parry"],
            "atacar": ["attack"],
            "ataque": ["attack"],
            "golpear": ["attack"],
            "salvar": ["save"],
            "proteger": ["save"],
            "curar": ["heal"],
            "sanar": ["heal"],
            "restaurar": ["heal"],
        }
        
        # Create reverse lookup for faster matching
        self.command_to_action = {}
        for action, commands in self.exact_commands.items():
            if action in self.action_types:
                for cmd in commands:
                    self.command_to_action[cmd.lower()] = action
            else:
                # It's a translation, map to the action
                for target_action in commands:
                    self.command_to_action[action.lower()] = target_action
    
    def _init_regex_patterns(self):
        """Initialize pre-compiled regex patterns (second layer)."""
        self.regex_patterns = {
            "evade": [
                re.compile(r'\b(dodge|evade|avoid|sidestep|duck|get\s+out|move\s+away)\b', re.IGNORECASE),
                re.compile(r'\b(esquiv|esquiv[oaó])\b', re.IGNORECASE),
                re.compile(r'\b(me\s+quito|me\s+muevo)\b', re.IGNORECASE),
            ],
            "parry": [
                re.compile(r'\b(parry|block|deflect|counter|shield)\b', re.IGNORECASE),
                re.compile(r'\b(par[oaó]|bloque[oaó]|defiendo)\b', re.IGNORECASE),
            ],
            "attack": [
                re.compile(r'\b(attack|strike|hit|slash|punch|kick|shoot|fire)\b', re.IGNORECASE),
                re.compile(r'\b(atac|golpe[oaó]|peg[oaó]|disparo)\b', re.IGNORECASE),
                re.compile(r'\batting\s+(back|again|now)\b', re.IGNORECASE),
            ],
            "save": [
                re.compile(r'\b(save|rescue|protect|guard|defend)\b', re.IGNORECASE),
                re.compile(r'\b(salv[oaó]|proteg[oaó]|defiendo)\b', re.IGNORECASE),
            ],
            "heal": [
                re.compile(r'\b(heal|restore|cure|mend|recover|revive)\b', re.IGNORECASE),
                re.compile(r'\b(cur[oaó]|san[oaó]|restaur[oaó])\b', re.IGNORECASE),
            ],
            "power1": [
                re.compile(r'\b(power\s*1|special\s*1|ability\s*1|skill\s*1|ultimate)\b', re.IGNORECASE),
            ],
            "power2": [
                re.compile(r'\b(power\s*2|special\s*2|ability\s*2|skill\s*2)\b', re.IGNORECASE),
            ],
        }
    
    def _init_nlp_models(self):
        """Initialize spaCy NLP models (third layer, most powerful)."""
        self.nlp_enabled = self.config.get("enable_nlp", True)
        self.nlp_models = {}
        
        if not self.nlp_enabled:
            logger.info("NLP layer disabled")
            return
        
        try:
            import spacy
            from spacy_langdetect import LanguageDetector
            from spacy.language import Language
            
            # Load lightweight models
            try:
                self.nlp_models['en'] = spacy.load("en_core_web_sm")
                logger.info("English NLP model loaded")
            except OSError:
                logger.warning("English model not found. Run: python -m spacy download en_core_web_sm")
            
            try:
                self.nlp_models['es'] = spacy.load("es_core_news_sm")
                logger.info("Spanish NLP model loaded")
            except OSError:
                logger.warning("Spanish model not found. Run: python -m spacy download es_core_news_sm")
            
            # Add language detector to English model
            if 'en' in self.nlp_models and self.config.get("enable_language_detection", True):
                @Language.factory("language_detector")
                def create_language_detector(nlp, name):
                    return LanguageDetector()
                
                if "language_detector" not in self.nlp_models['en'].pipe_names:
                    self.nlp_models['en'].add_pipe("language_detector", last=True)
            
            # Action verb lemmas for matching
            self.action_verbs = {
                "evade": {"dodge", "evade", "avoid", "sidestep", "duck", "esquivar"},
                "parry": {"parry", "block", "deflect", "counter", "parar", "bloquear"},
                "attack": {"attack", "strike", "hit", "slash", "punch", "kick", "shoot", "atacar", "golpear"},
                "save": {"save", "rescue", "protect", "guard", "defend", "salvar", "proteger"},
                "heal": {"heal", "restore", "cure", "mend", "recover", "curar", "sanar"},
                "power1": {"power", "special", "ability", "skill", "ultimate"},
                "power2": {"power", "special", "ability", "skill"},
            }
            
        except ImportError as e:
            logger.error(f"spaCy or langdetect not installed: {e}")
            self.nlp_enabled = False
    
    def detect(self, text: str) -> Tuple[Optional[str], float]:
        """
        Detect action from text with confidence score.
        Returns: (action_type, confidence)
        """
        start_time = time.time()
        
        # Layer 0: Creative moves
        action, confidence = self._creative_move_match(text)
        if action:
            self._cache_result(text.lower().strip(), action, confidence)
            self._update_stats(time.time() - start_time, "creative")
            return action, confidence
        
        # Layer 0: Creative moves
        action, confidence = self._creative_move_match(text)
        if action:
            self._cache_result(cache_key, action, confidence)
            self._update_stats(time.time() - start_time, "creative")
            return action, confidence
        
        # Check cache first
        cache_key = text.lower().strip()
        if cache_key in self.pattern_cache:
            action, confidence = self.pattern_cache[cache_key]
            self._update_stats(time.time() - start_time, "cache")
            return action, confidence
        
        # Layer 1: Exact command matching (fastest, highest confidence)
        action, confidence = self._exact_match(text)
        if action:
            self._cache_result(cache_key, action, confidence)
            self._update_stats(time.time() - start_time, "exact")
            return action, confidence
        
        # Layer 2: Regex pattern matching (fast, good confidence)
        action, confidence = self._regex_match(text)
        if action and confidence >= self.config["confidence_threshold"]:
            self._cache_result(cache_key, action, confidence)
            self._update_stats(time.time() - start_time, "regex")
            return action, confidence
        
        # Layer 3: NLP analysis (slower, context-aware, moderate confidence)
        if self.nlp_enabled:
            action, confidence = self._nlp_match(text)
            if action and confidence >= self.config["confidence_threshold"]:
                self._cache_result(cache_key, action, confidence)
                self._update_stats(time.time() - start_time, "nlp")
                return action, confidence
        
        # No match found
        self._update_stats(time.time() - start_time, "none")
        return None, 0.0
    
    def _creative_move_match(self, text: str) -> Tuple[Optional[str], float]:
        """Layer 0: Creative move matching."""
        lower_text = text.lower()
        for move, data in self.creative_moves.items():
            for trigger in data["triggers"]:
                if trigger in lower_text:
                    return move, 1.0
        return None, 0.0

    def _exact_match(self, text: str) -> Tuple[Optional[str], float]:
        """Layer 1: Exact command matching."""
        words = text.lower().strip().split()
        
        for word in words:
            if word in self.command_to_action:
                return self.command_to_action[word], 1.0
        
        return None, 0.0
    
    def _regex_match(self, text: str) -> Tuple[Optional[str], float]:
        """Layer 2: Regex pattern matching."""
        best_match = None
        best_confidence = 0.0
        
        for action, patterns in self.regex_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    confidence = 0.85  # High confidence for regex match
                    if confidence > best_confidence:
                        best_match = action
                        best_confidence = confidence
        
        return best_match, best_confidence
    
    def _nlp_match(self, text: str) -> Tuple[Optional[str], float]:
        """Layer 3: NLP-based matching with lemmatization."""
        if not self.nlp_models:
            return None, 0.0
        
        # Detect language
        lang = 'en'  # Default
        if self.config.get("enable_language_detection", True) and 'en' in self.nlp_models:
            try:
                doc = self.nlp_models['en'](text)
                if hasattr(doc._, 'language'):
                    detected_lang = doc._.language['language']
                    if detected_lang == 'es' and 'es' in self.nlp_models:
                        lang = 'es'
            except Exception:
                pass
        
        # Process with appropriate model
        nlp = self.nlp_models.get(lang)
        if not nlp:
            return None, 0.0
        
        try:
            doc = nlp(text)
            
            # Extract verbs and their lemmas
            verbs = []
            for token in doc:
                if token.pos_ == "VERB":
                    verbs.append(token.lemma_.lower())
            
            # Match against action verbs
            best_match = None
            best_confidence = 0.0
            
            for action, verb_set in self.action_verbs.items():
                for verb in verbs:
                    if verb in verb_set:
                        confidence = 0.75  # Moderate confidence for NLP match
                        if confidence > best_confidence:
                            best_match = action
                            best_confidence = confidence
            
            return best_match, best_confidence
            
        except Exception as e:
            logger.error(f"NLP processing error: {e}")
            return None, 0.0
    
    def _cache_result(self, key: str, action: str, confidence: float):
        """Cache detection result."""
        if len(self.pattern_cache) >= self.max_cache_size:
            # Remove oldest entries (simple FIFO)
            to_remove = list(self.pattern_cache.keys())[:100]
            for k in to_remove:
                del self.pattern_cache[k]
        
        self.pattern_cache[key] = (action, confidence)
    
    def _update_stats(self, detection_time: float, match_type: str):
        """Update performance statistics."""
        self.stats["total_detections"] += 1
        self.stats["total_time"] += detection_time
        self.stats["avg_detection_time"] = (
            self.stats["total_time"] / self.stats["total_detections"]
        )
        
        if match_type == "exact":
            self.stats["exact_matches"] += 1
        elif match_type == "regex":
            self.stats["regex_matches"] += 1
        elif match_type == "nlp":
            self.stats["nlp_matches"] += 1
    
    def add_pattern(self, action: str, pattern: str, pattern_type: str = "regex"):
        """
        Dynamically add a new detection pattern.
        
        Args:
            action: Action type (evade, parry, etc.)
            pattern: Pattern string
            pattern_type: 'exact' or 'regex'
        """
        if action not in self.action_types:
            logger.warning(f"Unknown action type: {action}")
            return False
        
        try:
            if pattern_type == "exact":
                self.command_to_action[pattern.lower()] = action
            elif pattern_type == "regex":
                compiled = re.compile(pattern, re.IGNORECASE)
                if action not in self.regex_patterns:
                    self.regex_patterns[action] = []
                self.regex_patterns[action].append(compiled)
            
            logger.info(f"Added {pattern_type} pattern for {action}: {pattern}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add pattern: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """Get performance statistics."""
        stats = self.stats.copy()
        
        # Calculate additional metrics
        if stats["total_detections"] > 0:
            stats["exact_match_rate"] = stats["exact_matches"] / stats["total_detections"]
            stats["regex_match_rate"] = stats["regex_matches"] / stats["total_detections"]
            stats["nlp_match_rate"] = stats["nlp_matches"] / stats["total_detections"]
            stats["avg_detection_time_ms"] = stats["avg_detection_time"] * 1000
        
        stats["cache_size"] = len(self.pattern_cache)
        stats["nlp_enabled"] = self.nlp_enabled
        
        return stats
    
    def reset_stats(self):
        """Reset performance statistics."""
        self.stats = {
            "total_detections": 0,
            "exact_matches": 0,
            "regex_matches": 0,
            "nlp_matches": 0,
            "avg_detection_time": 0.0,
            "total_time": 0.0,
            "accuracy_score": 0.0
        }
        logger.info("Statistics reset")
    
    def clear_cache(self):
        """Clear the pattern cache."""
        self.pattern_cache.clear()
        logger.info("Cache cleared")


# Test and benchmark function
def benchmark_detector(iterations: int = 1000):
    """Benchmark the detector with various inputs."""
    print("\n" + "="*60)
    print("NLP Action Detector Benchmark")
    print("="*60)
    
    detector = ActionDetector()
    
    test_cases = [
        ("evade", "I dodge!"),
        ("evade", "esquivo!"),
        ("attack", "attacking back"),
        ("attack", "I'm going to hit him"),
        ("parry", "block that!"),
        ("heal", "time to heal"),
        ("save", "I'll protect you"),
        ("evade", "me quito de ahí"),
        ("attack", "golpeo fuerte"),
        ("parry", "defiendo"),
    ]
    
    print(f"\nRunning {len(test_cases)} test cases {iterations} times each...\n")
    
    correct = 0
    total = 0
    times = []
    
    for expected_action, text in test_cases:
        for _ in range(iterations):
            start = time.time()
            action, confidence = detector.detect(text)
            elapsed = (time.time() - start) * 1000  # ms
            times.append(elapsed)
            
            total += 1
            if action == expected_action:
                correct += 1
    
    accuracy = (correct / total) * 100
    avg_time = sum(times) / len(times)
    
    print(f"Test Results:")
    print(f"  Total tests: {total}")
    print(f"  Correct: {correct}")
    print(f"  Accuracy: {accuracy:.2f}%")
    print(f"  Avg detection time: {avg_time:.3f}ms")
    print(f"  Min time: {min(times):.3f}ms")
    print(f"  Max time: {max(times):.3f}ms")
    
    stats = detector.get_stats()
    print(f"\nDetection Method Breakdown:")
    print(f"  Exact matches: {stats['exact_matches']} ({stats.get('exact_match_rate', 0)*100:.1f}%)")
    print(f"  Regex matches: {stats['regex_matches']} ({stats.get('regex_match_rate', 0)*100:.1f}%)")
    print(f"  NLP matches: {stats['nlp_matches']} ({stats.get('nlp_match_rate', 0)*100:.1f}%)")
    print(f"  Cache size: {stats['cache_size']}")
    
    print("\n" + "="*60)
    
    return detector


if __name__ == "__main__":
    # Run benchmark when executed directly
    detector = benchmark_detector(iterations=100)
    
    # Interactive testing
    print("\nInteractive Testing (type 'quit' to exit):")
    while True:
        try:
            text = input("\nEnter text to detect action: ").strip()
            if text.lower() in ['quit', 'exit', 'q']:
                break
            
            if not text:
                continue
            
            start = time.time()
            action, confidence = detector.detect(text)
            elapsed = (time.time() - start) * 1000
            
            if action:
                print(f"  ✓ Action: {action}")
                print(f"  ✓ Confidence: {confidence:.2f}")
                print(f"  ✓ Time: {elapsed:.3f}ms")
            else:
                print(f"  ✗ No action detected")
                print(f"  ✗ Time: {elapsed:.3f}ms")
        
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"  ✗ Error: {e}")
