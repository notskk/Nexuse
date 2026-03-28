import sys
import base64
import zstandard as zstd
import io
import json
from copy import deepcopy

# -----------------------------
# Helpers
# -----------------------------

def expand_nested_data(obj):
    if isinstance(obj, list):
        return [expand_nested_data(i) for i in obj]
    elif isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if k.upper() == "DATA" and isinstance(v, str):
                try:
                    new_obj[k] = expand_nested_data(json.loads(v))
                except json.JSONDecodeError:
                    new_obj[k] = v
            else:
                new_obj[k] = expand_nested_data(v)
        return new_obj
    else:
        return obj

def collapse_nested_data(obj):
    if isinstance(obj, list):
        return [collapse_nested_data(i) for i in obj]
    elif isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if k.upper() == "DATA" and isinstance(v, (dict, list)):
                new_obj[k] = json.dumps(v, separators=(',', ':'))
            else:
                new_obj[k] = collapse_nested_data(v)
        return new_obj
    else:
        return obj

# -----------------------------
# Encode / Decode
# -----------------------------

def encode_file(input_file, output_file=None):
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()

    # Before encoding, collapse DATA objects back into strings
    try:
        parsed = json.loads(text)
        collapsed = collapse_nested_data(parsed)
        text_to_encode = json.dumps(collapsed, separators=(',', ':'))
    except:
        text_to_encode = text

    cctx = zstd.ZstdCompressor()
    compressed_bytes = cctx.compress(text_to_encode.encode('utf-8'))
    b64_text = base64.b64encode(compressed_bytes).decode('utf-8')

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(b64_text)
        print(f"Encoded Base64+zstd saved to {output_file}")
    else:
        print(b64_text)

def decode_file(input_file, output_file=None):
    with open(input_file, 'r', encoding='utf-8') as f:
        b64_text = f.read().strip().strip('"')

    try:
        compressed_bytes = base64.b64decode(b64_text)
    except Exception as e:
        print("Error decoding Base64:", e)
        return

    try:
        compressed_stream = io.BytesIO(compressed_bytes)
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(compressed_stream) as reader:
            decompressed_bytes = reader.read()
        text = decompressed_bytes.decode('utf-8')
    except Exception as e:
        print("Error decompressing zstd:", e)
        return

    # Pretty print JSON
    try:
        parsed = json.loads(text)
        expanded = expand_nested_data(parsed)
        pretty_text = json.dumps(expanded, indent=4, ensure_ascii=False)
    except:
        pretty_text = text

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(pretty_text)
        print(f"Decoded JSON saved (pretty) to {output_file}")
    else:
        print(pretty_text)

# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python zstd_tool.py encode|decode")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == 'decode':
        input_file = "code.txt"
        output_file = "timeline.json"
        decode_file(input_file, output_file)

    elif command == 'encode':
        input_file = "timeline.json"
        output_file = "code.txt"
        encode_file(input_file, output_file)

    else:
        print("Invalid command! Use 'encode' or 'decode'.")