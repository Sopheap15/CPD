#!/usr/bin/env python3
# Fix the indentation in registration.py

with open(r"C:\Users\osopheap\Desktop\CPD\cpd\handlers\registration.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the except lines with proper indentation (4 spaces)
content = content.replace(
    "except asyncio.TimeoutError:",
    "    except asyncio.TimeoutError:"
)

content = content.replace(
    "except Exception as exc:",
    "    except Exception as exc:"
)

with open(r"C:\Users\osopheap\Desktop\CPD\cpd\handlers\registration.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed indentation in registration.py")