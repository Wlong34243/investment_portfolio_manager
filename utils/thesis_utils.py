import re
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from ruamel.yaml import YAML
import io

class ThesisManager:
    """
    Manages the parsing and updating of investment thesis markdown files.
    Supports frontmatter, fenced YAML triggers, and HTML-comment regions.
    """
    
    REGION_START_PATTERN = r"<!-- region:{} -->"
    REGION_END_PATTERN = r"<!-- endregion:{} -->"
    
    # Matches any region: <!-- region:name --> ... <!-- endregion:name -->
    ANY_REGION_PATTERN = re.compile(
        r"<!-- region:(?P<name>\w+) -->\s*\n(?P<content>.*?)<!-- endregion:\1 -->",
        re.DOTALL
    )
    
    # Matches frontmatter: --- ... ---
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    
    # Matches fenced YAML triggers: ```yaml\ntriggers:\n...```
    TRIGGERS_BLOCK_PATTERN = re.compile(
        r"```yaml\s*\ntriggers:\s*\n(?P<content>.*?)```",
        re.DOTALL
    )

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.raw_content = file_path.read_text(encoding="utf-8")
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.indent(mapping=2, sequence=4, offset=2)

    def get_frontmatter(self) -> Optional[Dict]:
        match = self.FRONTMATTER_PATTERN.search(self.raw_content)
        if match:
            return self.yaml.load(match.group(1))
        return None

    def get_triggers(self) -> Optional[Dict]:
        match = self.TRIGGERS_BLOCK_PATTERN.search(self.raw_content)
        if match:
            # Add 'triggers:' back to make it valid YAML for the parser
            return self.yaml.load("triggers:\n" + match.group("content"))
        return None

    def get_regions(self) -> Dict[str, str]:
        return {m.group("name"): m.group("content").strip() for m in self.ANY_REGION_PATTERN.finditer(self.raw_content)}

    def replace_region(self, name: str, new_content: str) -> str:
        """
        Replaces an existing region or appends it to the end of the file if not found.
        """
        pattern = re.compile(
            rf"<!-- region:{name} -->\s*\n(.*?)\n?<!-- endregion:{name} -->",
            re.DOTALL
        )
        
        replacement = f"<!-- region:{name} -->\n{new_content.strip()}\n<!-- endregion:{name} -->"
        
        if pattern.search(self.raw_content):
            self.raw_content = pattern.sub(replacement, self.raw_content)
        else:
            # Append to the end, ensuring there's a newline before
            if not self.raw_content.endswith("\n"):
                self.raw_content += "\n"
            self.raw_content += "\n" + replacement + "\n"
        
        return self.raw_content

    def update_frontmatter(self, updates: Dict) -> str:
        match = self.FRONTMATTER_PATTERN.search(self.raw_content)
        if not match:
            # If no frontmatter, prepend it (rare for this project)
            data = updates
            stream = io.StringIO()
            self.yaml.dump(data, stream)
            self.raw_content = f"---\n{stream.getvalue()}---\n\n" + self.raw_content
            return self.raw_content

        data = self.yaml.load(match.group(1)) or {}
        data.update(updates)
        
        stream = io.StringIO()
        self.yaml.dump(data, stream)
        new_fm = f"---\n{stream.getvalue()}---"
        
        self.raw_content = self.FRONTMATTER_PATTERN.sub(new_fm + "\n", self.raw_content)
        return self.raw_content

    def update_triggers(self, updates: Dict) -> str:
        """
        Updates the triggers block while preserving comments and order.
        """
        match = self.TRIGGERS_BLOCK_PATTERN.search(self.raw_content)
        if not match:
            return self.raw_content

        # Load the content as triggers. We prepend 'triggers:\n' to keep the structure.
        # But we need to make sure we don't lose the indentation of the original content.
        raw_triggers_content = match.group("content")
        
        # Use a temporary YAML object for this specific block to control its formatting
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)
        # Preserve 'null' as 'null' instead of empty
        def represent_none(self, data):
            return self.represent_scalar(u'tag:yaml.org,2002:null', u'null')
        yaml.representer.add_representer(type(None), represent_none)

        try:
            # We load the whole block including 'triggers:' if we can, 
            # but the pattern only captured the content.
            # Let's try to load it with a dummy top level.
            data = yaml.load("triggers:\n" + raw_triggers_content)
            if not data or "triggers" not in data:
                return self.raw_content
                
            for k, v in updates.items():
                data["triggers"][k] = v
            
            stream = io.StringIO()
            yaml.dump(data["triggers"], stream)
            
            # The dumped content might have a trailing newline, and we want to 
            # re-indent it if it was indented in the original.
            # But wait, the original was indented by 2 spaces.
            new_content_lines = stream.getvalue().splitlines()
            # Most theses have 2 spaces indentation for trigger values
            indented_content = "\n".join(["  " + line for line in new_content_lines]) + "\n"
            
            new_block = f"```yaml\ntriggers:\n{indented_content}```"
            self.raw_content = self.TRIGGERS_BLOCK_PATTERN.sub(new_block, self.raw_content)
        except Exception as e:
            logging.error(f"Failed to update triggers YAML: {e}")
            
        return self.raw_content

    def save(self, backup: bool = False):
        if backup:
            # Fix: replace colons with dashes for Windows filename compatibility
            timestamp = datetime.now().isoformat().replace(":", "-")
            backup_path = self.file_path.with_suffix(f"{self.file_path.suffix}.bak.{timestamp}")
            backup_path.write_text(self.file_path.read_text(encoding="utf-8"), encoding="utf-8")
        
        self.file_path.write_text(self.raw_content, encoding="utf-8")

if __name__ == "__main__":
    # Quick smoke test
    test_path = Path("vault/theses/UNH_thesis.md")
    if test_path.exists():
        mgr = ThesisManager(test_path)
        print("Frontmatter:", mgr.get_frontmatter())
        print("Triggers:", mgr.get_triggers())
        print("Regions:", mgr.get_regions())
        
        # Test updating a region
        mgr.replace_region("change_log", "2026-05-03: Initial sync test.")
        print("Updated content sample:", mgr.raw_content[-150:])
