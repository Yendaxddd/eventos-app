"""
Changelog Management System
Tracks code changes, features, and updates
Author: Kilo Code
Version: 3.0.0
"""

import json
import os
import hashlib
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChangelogManager:
    """
    Manages changelog entries with automatic tracking and manual entry support.
    """
    
    def __init__(self, changelog_path: str = "dashboard/changelog.json"):
        """Initialize the changelog manager."""
        self.changelog_path = changelog_path
        self.changelog_dir = os.path.dirname(changelog_path)
        self.backup_dir = os.path.join(self.changelog_dir, "backups")
        
        # Create directories if they don't exist
        os.makedirs(self.changelog_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Load existing changelog or create new
        self.changelog = self._load_changelog()
        
        # File tracking for auto-detection
        self.tracked_files = {}
        self._init_file_tracking()
        
        logger.info(f"ChangelogManager initialized: {changelog_path}")
    
    def _load_changelog(self) -> Dict:
        """Load existing changelog or create a new one."""
        if os.path.exists(self.changelog_path):
            try:
                with open(self.changelog_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Loaded changelog with {len(data.get('changes', []))} entries")
                    return data
            except Exception as e:
                logger.error(f"Error loading changelog: {e}")
        
        # Create new changelog structure
        return {
            "version": "3.0.0",
            "project": "NLP Action Detection System",
            "created": datetime.utcnow().isoformat() + "Z",
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "changes": []
        }
    
    def _save_changelog(self, create_backup: bool = True):
        """Save changelog to file with optional backup."""
        if create_backup and os.path.exists(self.changelog_path):
            self._create_backup()
        
        self.changelog["last_updated"] = datetime.utcnow().isoformat() + "Z"
        
        try:
            with open(self.changelog_path, 'w', encoding='utf-8') as f:
                json.dump(self.changelog, f, indent=2, ensure_ascii=False)
            logger.info("Changelog saved successfully")
        except Exception as e:
            logger.error(f"Error saving changelog: {e}")
    
    def _create_backup(self):
        """Create a backup of the current changelog."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"changelog_backup_{timestamp}.json")
            
            with open(self.changelog_path, 'r', encoding='utf-8') as src:
                with open(backup_path, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
            
            logger.info(f"Backup created: {backup_path}")
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    def _init_file_tracking(self):
        """Initialize file tracking for auto-detection."""
        # Track key project files
        files_to_track = [
            "nlp_detector.py",
            "changelog_manager.py",
            "dashboard/app.py",
            "advanced_qte_hp_system_debug.py",
            "config.json"
        ]
        
        for filepath in files_to_track:
            if os.path.exists(filepath):
                self.tracked_files[filepath] = self._get_file_hash(filepath)
    
    def _get_file_hash(self, filepath: str) -> str:
        """Get MD5 hash of a file."""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def add_change(
        self,
        title: str,
        description: str,
        category: str = "feature",
        author: str = "Scorp",
        files_changed: Optional[List[str]] = None,
        impact: str = "medium",
        version: Optional[str] = None
    ) -> str:
        """
        Add a new changelog entry.
        
        Args:
            title: Short title of the change
            description: Detailed description
            category: Type of change (feature, bugfix, optimization, documentation)
            author: Author of the change
            files_changed: List of modified files
            impact: Impact level (low, medium, high, critical)
            version: Optional version number
        
        Returns:
            Change ID
        """
        change_id = self._generate_change_id()
        
        change_entry = {
            "id": change_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "author": author,
            "category": category,
            "title": title,
            "description": description,
            "files_changed": files_changed or [],
            "impact": impact,
            "version": version or self.changelog["version"]
        }
        
        self.changelog["changes"].insert(0, change_entry)  # Add to beginning
        self._save_changelog()
        
        logger.info(f"Added changelog entry: {change_id} - {title}")
        return change_id
    
    def _generate_change_id(self) -> str:
        """Generate a unique change ID."""
        existing_ids = [c["id"] for c in self.changelog["changes"]]
        
        # Extract numeric part from IDs like "c001", "c002"
        numbers = []
        for cid in existing_ids:
            if cid.startswith("c") and cid[1:].isdigit():
                numbers.append(int(cid[1:]))
        
        next_num = max(numbers) + 1 if numbers else 1
        return f"c{next_num:03d}"
    
    def detect_changes(self) -> List[Dict]:
        """
        Auto-detect file changes since last check.
        
        Returns:
            List of detected changes
        """
        detected = []
        
        for filepath, old_hash in self.tracked_files.items():
            if not os.path.exists(filepath):
                continue
            
            new_hash = self._get_file_hash(filepath)
            if new_hash != old_hash and new_hash != "":
                detected.append({
                    "file": filepath,
                    "old_hash": old_hash,
                    "new_hash": new_hash
                })
                self.tracked_files[filepath] = new_hash
        
        return detected
    
    def update_version(self, new_version: str):
        """Update the project version."""
        old_version = self.changelog["version"]
        self.changelog["version"] = new_version
        
        self.add_change(
            title=f"Version Update: {old_version} → {new_version}",
            description=f"Project version updated from {old_version} to {new_version}",
            category="release",
            impact="high"
        )
        
        logger.info(f"Version updated: {old_version} → {new_version}")
    
    def get_changes(
        self,
        category: Optional[str] = None,
        author: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get changelog entries with optional filtering.
        
        Args:
            category: Filter by category
            author: Filter by author
            limit: Maximum number of entries to return
        
        Returns:
            List of changelog entries
        """
        changes = self.changelog["changes"]
        
        # Apply filters
        if category:
            changes = [c for c in changes if c["category"] == category]
        
        if author:
            changes = [c for c in changes if c["author"] == author]
        
        # Apply limit
        if limit:
            changes = changes[:limit]
        
        return changes
    
    def search_changes(self, query: str) -> List[Dict]:
        """
        Search changelog entries by text.
        
        Args:
            query: Search query
        
        Returns:
            List of matching entries
        """
        query_lower = query.lower()
        results = []
        
        for change in self.changelog["changes"]:
            # Search in title and description
            if (query_lower in change["title"].lower() or 
                query_lower in change["description"].lower()):
                results.append(change)
        
        return results
    
    def export_markdown(self, output_path: str = "CHANGELOG.md"):
        """Export changelog to Markdown format."""
        try:
            lines = [
                f"# Changelog - {self.changelog['project']}",
                f"\nVersion: {self.changelog['version']}",
                f"\nLast Updated: {self.changelog['last_updated']}",
                "\n---\n"
            ]
            
            # Group by category
            categories = {}
            for change in self.changelog["changes"]:
                cat = change["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(change)
            
            # Write each category
            category_names = {
                "feature": "✨ Features",
                "bugfix": "🐛 Bug Fixes",
                "optimization": "⚡ Optimizations",
                "documentation": "📝 Documentation",
                "release": "🚀 Releases"
            }
            
            for cat, cat_changes in categories.items():
                cat_name = category_names.get(cat, cat.title())
                lines.append(f"\n## {cat_name}\n")
                
                for change in cat_changes:
                    timestamp = datetime.fromisoformat(change["timestamp"].replace("Z", "+00:00"))
                    date_str = timestamp.strftime("%Y-%m-%d")
                    
                    lines.append(f"\n### {change['title']}")
                    lines.append(f"**Date:** {date_str} | **Author:** {change['author']} | **Impact:** {change['impact']}")
                    lines.append(f"\n{change['description']}")
                    
                    if change.get("files_changed"):
                        lines.append("\n**Files Changed:**")
                        for file in change["files_changed"]:
                            lines.append(f"- `{file}`")
                    
                    lines.append("\n---")
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            logger.info(f"Exported changelog to {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error exporting markdown: {e}")
            return False
    
    def export_html(self, output_path: str = "changelog.html"):
        """Export changelog to HTML format."""
        try:
            html = [
                "<!DOCTYPE html>",
                "<html lang='en'>",
                "<head>",
                "    <meta charset='UTF-8'>",
                "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
                f"    <title>Changelog - {self.changelog['project']}</title>",
                "    <style>",
                "        body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 40px; background: #1a1a1a; color: #e0e0e0; }",
                "        h1 { color: #00d4ff; }",
                "        h2 { color: #ff6b6b; margin-top: 30px; }",
                "        h3 { color: #4ecdc4; }",
                "        .change { background: #2a2a2a; padding: 20px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #00d4ff; }",
                "        .meta { color: #888; font-size: 0.9em; }",
                "        .files { background: #1a1a1a; padding: 10px; border-radius: 4px; margin-top: 10px; }",
                "        code { background: #3a3a3a; padding: 2px 6px; border-radius: 3px; color: #ff6b6b; }",
                "    </style>",
                "</head>",
                "<body>",
                f"    <h1>📋 {self.changelog['project']} Changelog</h1>",
                f"    <p><strong>Version:</strong> {self.changelog['version']}</p>",
                f"    <p><strong>Last Updated:</strong> {self.changelog['last_updated']}</p>",
                "    <hr>"
            ]
            
            for change in self.changelog["changes"]:
                timestamp = datetime.fromisoformat(change["timestamp"].replace("Z", "+00:00"))
                date_str = timestamp.strftime("%Y-%m-%d %H:%M")
                
                html.append("    <div class='change'>")
                html.append(f"        <h3>{change['title']}</h3>")
                html.append(f"        <p class='meta'>{date_str} | {change['author']} | {change['category']} | Impact: {change['impact']}</p>")
                html.append(f"        <p>{change['description']}</p>")
                
                if change.get("files_changed"):
                    html.append("        <div class='files'>")
                    html.append("            <strong>Files Changed:</strong><br>")
                    for file in change["files_changed"]:
                        html.append(f"            <code>{file}</code><br>")
                    html.append("        </div>")
                
                html.append("    </div>")
            
            html.extend(["</body>", "</html>"])
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(html))
            
            logger.info(f"Exported changelog to {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error exporting HTML: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """Get changelog statistics."""
        total = len(self.changelog["changes"])
        
        categories = {}
        authors = {}
        impacts = {}
        
        for change in self.changelog["changes"]:
            # Count by category
            cat = change["category"]
            categories[cat] = categories.get(cat, 0) + 1
            
            # Count by author
            auth = change["author"]
            authors[auth] = authors.get(auth, 0) + 1
            
            # Count by impact
            imp = change["impact"]
            impacts[imp] = impacts.get(imp, 0) + 1
        
        return {
            "total_changes": total,
            "by_category": categories,
            "by_author": authors,
            "by_impact": impacts,
            "current_version": self.changelog["version"],
            "last_updated": self.changelog["last_updated"]
        }


# Utility function to quickly add a change
def quick_add(title: str, description: str, **kwargs):
    """Quick function to add a changelog entry."""
    manager = ChangelogManager()
    return manager.add_change(title, description, **kwargs)


if __name__ == "__main__":
    # Example usage and testing
    print("="*60)
    print("Changelog Manager Test")
    print("="*60)
    
    manager = ChangelogManager()
    
    # Add some example changes
    print("\nAdding example changes...")
    
    manager.add_change(
        title="NLP Action Detection System",
        description="Implemented multi-layer NLP detection with English and Spanish support",
        category="feature",
        files_changed=["nlp_detector.py"],
        impact="high"
    )
    
    manager.add_change(
        title="Web Dashboard",
        description="Created Flask-based real-time dashboard with WebSocket support",
        category="feature",
        files_changed=["dashboard/app.py", "dashboard/templates/index.html"],
        impact="high"
    )
    
    manager.add_change(
        title="Changelog System",
        description="Automatic change tracking with export to Markdown and HTML",
        category="feature",
        files_changed=["changelog_manager.py"],
        impact="medium"
    )
    
    # Display statistics
    print("\nChangelog Statistics:")
    stats = manager.get_statistics()
    print(f"  Total changes: {stats['total_changes']}")
    print(f"  Current version: {stats['current_version']}")
    print(f"\nBy category:")
    for cat, count in stats['by_category'].items():
        print(f"    {cat}: {count}")
    
    # Export
    print("\nExporting changelog...")
    manager.export_markdown("CHANGELOG.md")
    manager.export_html("changelog.html")
    
    print("\n✓ Changelog manager test complete!")
    print("="*60)