#!/usr/bin/env python3
"""
Fix indentation error in utils/text_segmentation.py
Ensures proper spacing and removes any mixed tabs/spaces
"""

import re
import os

def fix_indentation():
    """Fix the indentation error in text_segmentation.py"""
    
    file_path = "utils/text_segmentation.py"
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    print(f"🔧 Fixing indentation in {file_path}")
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # The problematic section around line 302-304
    # Fix the specific indentation issue
    problematic_pattern = r'''(\s+elif "translated_text" in result:\s*\n\s+# Legacy format \(just translated_text\)\s*\n)(\s*translated_text = result\["translated_text"\]\.replace\('<\/br>', '\\n'\)\s*\n\s+success = True)'''
    
    fixed_replacement = r'''\1                    translated_text = result["translated_text"].replace('</br>', '\n')
                    success = True'''
    
    # Apply the fix
    new_content = re.sub(problematic_pattern, fixed_replacement, content, flags=re.MULTILINE)
    
    # Also ensure all indentation uses spaces (4 spaces per level)
    lines = new_content.split('\n')
    fixed_lines = []
    
    for line_num, line in enumerate(lines, 1):
        # Replace tabs with 4 spaces
        line = line.expandtabs(4)
        
        # Check for the specific problematic area and ensure proper indentation
        if line_num >= 300 and line_num <= 310:
            # Ensure proper indentation for this critical section
            if 'elif "translated_text" in result:' in line:
                line = '                elif "translated_text" in result:'
            elif '# Legacy format (just translated_text)' in line:
                line = '                    # Legacy format (just translated_text)'
            elif 'translated_text = result["translated_text"]' in line and 'elif' in lines[line_num-3]:
                line = '                    translated_text = result["translated_text"].replace(\'</br>\', \'\\n\')'
            elif 'success = True' in line and 'translated_text = result["translated_text"]' in lines[line_num-2]:
                line = '                    success = True'
        
        fixed_lines.append(line)
    
    new_content = '\n'.join(fixed_lines)
    
    # Write the fixed content back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ Fixed indentation in {file_path}")
    
    # Verify Python syntax
    try:
        import py_compile
        py_compile.compile(file_path, doraise=True)
        print(f"✅ Python syntax is valid in {file_path}")
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error still exists: {e}")
        return False

if __name__ == "__main__":
    success = fix_indentation()
    exit(0 if success else 1) 