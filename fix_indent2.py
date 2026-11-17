#!/usr/bin/env python3
with open("backend/stock_predictor_server/services/market_data.py", "r") as f:
    lines = f.readlines()

# Find the problematic except block and fix it
for i, line in enumerate(lines):
    if "except Exception as e:" in line:
        # Check the next line
        if i + 1 < len(lines) and lines[i + 1].startswith("            pass"):
            # Replace with 16-space indented pass
            lines[i + 1] = "                pass\n"
            with open("backend/stock_predictor_server/services/market_data.py", "w") as f:
                f.writelines(lines)
            print(f"Fixed line {i+2}: pass now at 16-space indent")
            break
        elif i + 1 < len(lines) and lines[i + 1].startswith("            "):
            print(f"Line {i+2} already has indent: {repr(lines[i+1])}")
            # Check if it's just 'pass' without extra text
            stripped = lines[i + 1].strip()
            if stripped == "pass" or stripped.startswith("pass #"):
                lines[i + 1] = "                pass\n"
                with open("backend/stock_predictor_server/services/market_data.py", "w") as f:
                    f.writelines(lines)
                print("Fixed indentation")
                break
    if "pass  # empty except handler" in line:
        lines[i] = "            pass\n"
        with open("backend/stock_predictor_server/services/market_data.py", "w") as f:
            f.writelines(lines)
        print(f"Fixed line {i+1}")
        break
else:
    print("Pattern not found - checking line 206 manually")
    print(repr(lines[205]))
