"""
Extensions module for NRRD files.

This module implements the NRRD Extensions Specification, which adds support
for JSON-structured metadata while maintaining backward compatibility with
existing NRRD parsers.

The NRRD extension mechanism allows storing hierarchical, structured metadata in NRRD files
using a namespace-based approach. Extensions are declared in the NRRD header using the
'extensions' field, which maps namespace prefixes to URI identifiers.

Extension data is stored with keys prefixed by the namespace and a separator (default '/'):
- 'namespace/field': value
- 'namespace/nested.field': value  (hierarchical notation)

Example of extensions in a NRRD file:
```
NRRD0004
# ...standard NRRD fields...
extensions:={"meta":"https://example.org/meta/v1.0.0"}
meta/name:="My Dataset"
meta/creator:={"name":"John Doe","organization":"Example Org"}
meta/keywords:=["medical","imaging","example"]
```

When reading files, extension data is consolidated into the 'extensions' field in the header:
```python
{
    'extensions': {
        'meta': {
            'uri': 'https://example.org/meta/v1.0.0',
            'data': {
                'name': 'My Dataset',
                'creator': {
                    'name': 'John Doe',
                    'organization': 'Example Org'
                },
                'keywords': ['medical', 'imaging', 'example']
            }
        }
    }
}
```

This module provides the core functionality for parsing and generating extensions
in NRRD files, but most users will interact with extensions using the standard
nrrd.read() and nrrd.write() functions.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from nrrd.types import FlattenMode

# Type aliases
ExtensionName = str
ExtensionURI = str
ExtensionData = Dict[str, Any]
ExtensionObject = Dict[str, Any]  # { "uri": str, "data": Dict[str, Any] }
ExtensionsDict = Dict[ExtensionName, ExtensionObject]

# Constants
DEFAULT_NAMESPACE_SEPARATOR = "/"
DEFAULT_MAX_LINE_LENGTH = 78

# JSON serialization parameters
JSON_SEPARATORS = (',', ':')  # Compact JSON formatting

##############################################
# General-purpose flattening and reconstitution
##############################################

def flatten_structure(data, flatten: FlattenMode = "auto", max_length: int = 78, serializer=None):
    """
    A generator that flattens complex JSON structures using JSON Path–style keys,
    yielding one {path: value} dict per "line."
    
    :param data: A list of dicts, typically [{"key": <complex nested object>}].
    :param flatten:
        - "auto"   => Flatten only if the serialized length exceeds `max_length`.
        - "always" => Always flatten nested objects/lists.
        - "never"  => Never flatten, yield top-level objects intact.
    :param max_length: Nominal maximum serialized length for a single line (default 78).
    :param serializer: A function taking one dict and returning a string (default: json.dumps).
                       This is used to check line length for flatten="auto".
    :yield: A dict of the form { "path": value } for each flattened line.
    """
    if flatten not in {"auto", "always", "never"}:
        raise ValueError("flatten must be one of {'auto', 'always', 'never'}")
    if serializer is None:
        serializer = json.dumps
    if not isinstance(data, list) or len(data) == 0 or not isinstance(data[0], dict):
        raise ValueError("Input must be a list containing at least one dictionary")

    def fits_on_one_line(path, value):
        test_json = serializer({path: value})
        return len(test_json) <= max_length

    def should_flatten_path(path, value):
        if not isinstance(value, (dict, list)):
            return False
        if flatten == "always":
            return True
        if flatten == "never":
            return False
        return not fits_on_one_line(path, value)

    def process_value(path, value):
        if not should_flatten_path(path, value):
            yield {path: value}
            return
        if isinstance(value, dict):
            for k in sorted(value.keys()):
                sub_path = f"{path}.{k}" if path else k
                yield from process_value(sub_path, value[k])
        else:
            for i, elem in enumerate(value):
                sub_path = f"{path}[{i}]" if path else f"[{i}]"
                yield from process_value(sub_path, elem)

    if len(data) == 1 and len(data[0]) == 1:
        single_obj = data[0]
        (root_key, root_value), = single_obj.items()
        if flatten == "never":
            yield {root_key: root_value}
            return
        if should_flatten_path(root_key, root_value):
            yield from process_value(root_key, root_value)
        else:
            yield {root_key: root_value}
        return

    for obj in data:
        if flatten == "never":
            yield obj
            continue
        if flatten == "auto":
            obj_str = serializer(obj)
            if len(obj_str) <= max_length:
                yield obj
                continue
        for k in sorted(obj.keys()):
            yield from process_value(k, obj[k])


def reconstitute(flattened_list):
    """
    Reconstructs a nested Python dict from a list of flattened JSON Path–style entries.
    
    Each element of `flattened_list` must be a dict with exactly one key (e.g. {"a.b[0].c": value}).
    More specific paths override more general ones.
    
    :param flattened_list: A list of one-key dicts.
    :return: A nested Python dict with all entries merged.
    """
    entries = []
    for single_dict in flattened_list:
        if len(single_dict) != 1:
            raise ValueError("Each flattened entry must have exactly one key.")
        (path_string, value), = single_dict.items()
        tokens = _parse_json_path(path_string)
        entries.append((tokens, value))
    entries.sort(key=lambda x: len(x[0]))
    root = {}
    for tokens, val in entries:
        _set_value(root, tokens, val)
    return root


def _parse_json_path(path):
    """Parse a JSON path string into a list of tokens (strings and integers)."""
    parts = path.split('.')
    tokens = []
    bracket_pattern = re.compile(r'(.*?)\[(\d+)\](.*)')
    for part in parts:
        segment = part
        while segment:
            match = bracket_pattern.match(segment)
            if match:
                prefix, index_str, suffix = match.groups()
                if prefix:
                    tokens.append(prefix)
                tokens.append(int(index_str))
                segment = suffix
            else:
                tokens.append(segment)
                break
    return tokens


def _set_value(root, tokens, value):
    """Set a value in a nested structure based on JSON path tokens."""
    current = root
    for i, token in enumerate(tokens):
        is_last = (i == len(tokens) - 1)
        if is_last:
            if isinstance(token, int):
                if not isinstance(current, list):
                    current = []
                _ensure_list_size(current, token)
                current[token] = value
            else:
                if not isinstance(current, dict):
                    current = {}
                current[token] = value
            return _merge_into_root(root, tokens[:i], current)
        if isinstance(token, int):
            if not isinstance(current, list):
                new_list = []
                _ensure_list_size(new_list, token)
                _merge_into_root(root, tokens[:i], new_list)
                current = new_list
            _ensure_list_size(current, token)
            if current[token] is None:
                current[token] = {}
            current = current[token]
        else:
            if not isinstance(current, dict):
                new_dict = {}
                _merge_into_root(root, tokens[:i], new_dict)
                current = new_dict
            if token not in current or current[token] is None:
                current[token] = {}
            current = current[token]


def _ensure_list_size(lst, idx):
    """Ensure a list has enough elements to access the given index."""
    while len(lst) <= idx:
        lst.append(None)


def _merge_into_root(root, path_tokens, subtree):
    """Merge a subtree into a root structure at the given path."""
    if not path_tokens:
        return subtree
    current = root
    for i, token in enumerate(path_tokens):
        is_last = (i == len(path_tokens) - 1)
        if is_last:
            if isinstance(token, int):
                _ensure_list_size(current, token)
                current[token] = subtree
            else:
                current[token] = subtree
        else:
            if isinstance(token, int):
                _ensure_list_size(current, token)
                if current[token] is None:
                    current[token] = {}
                current = current[token]
            else:
                if token not in current or current[token] is None:
                    current[token] = {}
                current = current[token]
    return root


##############################################
# Application-specific namespace wrappers
##############################################

def flatten_namespaces(data, namespace_separator: str = "/", flatten: FlattenMode = "auto", max_length: int = 78, serializer=None):
    """
    A wrapper around flatten_structure() that accepts a dict whose top-level keys are namespaces.
    
    Each namespace's inner dict is transformed so that its keys are prefixed with
    "namespace{separator}".
    
    :param data: A dict mapping namespaces to dicts of key/value pairs.
                 Example:
                   { "meta": {"creator": "Alice", "date": "2023-03-15"},
                     "data": {"value1": "foo", "value2": "bar"} }
    :param namespace_separator: The separator joining the namespace and subkey.
                                e.g., ":" produces "meta:creator", "/" produces "meta/creator".
    :param flatten: "auto", "always", or "never" (passed to flatten_structure()).
    :param max_length: Maximum serialized length (passed to flatten_structure()).
    :param serializer: Custom serializer (passed to flatten_structure()).
    :yield: Flattened lines as dicts with keys like "namespace{separator}subkey[.more]".
    """
    list_of_dicts = []
    for ns, inner in data.items():
        if not isinstance(inner, dict):
            raise ValueError("Each namespace value must be a dictionary.")
        # Prepend the namespace and separator to each inner key.
        new_dict = {f"{ns}{namespace_separator}{k}": v for k, v in inner.items()}
        list_of_dicts.append(new_dict)
    yield from flatten_structure(list_of_dicts, flatten=flatten, max_length=max_length, serializer=serializer)


def reconstitute_namespaces(flattened_list, namespace_separator="/", namespace_list=None):
    """
    A wrapper around reconstitute() that rebuilds the namespaced nested structure.
    
    It expects flattened keys in the form "namespace{separator}subkey[.more]" and groups
    them by namespace. If namespace_list is provided, only keys whose namespace (the part before
    the separator) is in that list will be processed; all others are ignored.
    
    :param flattened_list: A list of flattened lines (each a dict with exactly one key)
         produced by flatten_namespaces().
    :param namespace_separator: The separator used between namespace and subkey.
    :param namespace_list: Optional list of allowed namespace names. Only lines with these
         namespaces will be processed.
    :return: A dict mapping namespaces to dicts of their key/value pairs.
             Example:
               { "meta": {"creator": "Alice", "date": "2023-03-15"},
                 "data": {"value1": "foo", "value2": "bar"} }
    """
    merged = reconstitute(flattened_list)
    namespaces = {}
    for key, value in merged.items():
        if namespace_separator in key:
            ns, subkey = key.split(namespace_separator, 1)
        else:
            continue
        if namespace_list is not None and ns not in namespace_list:
            continue
        if ns not in namespaces:
            namespaces[ns] = {}
        if subkey:
            namespaces[ns][subkey] = value
        else:
            namespaces[ns] = value
    return namespaces


# NRRD Extensions implementation
def parse_extensions_from_header(header: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract extension declarations from NRRD header.
    
    Supports two formats for extension declarations:
    1. Individual declarations with keys starting with 'extensions.'
    2. A single 'extensions' key with a JSON object containing all declarations
    
    Args:
        header: The NRRD header dictionary.
        
    Returns:
        A dictionary of extension names to URIs.
    """
    extensions = {}
    
    # First look for the singular 'extensions' key which contains multiple declarations
    if 'extensions' in header:
        ext_value = header['extensions']
        
        # Ensure the value is properly parsed from JSON if needed
        if isinstance(ext_value, str):
            try:
                ext_value = json.loads(ext_value)
            except json.JSONDecodeError:
                # If parsing fails, it's not a valid JSON object, so we ignore it
                pass
        
        # If it's a dictionary after parsing, add all entries to extensions
        if isinstance(ext_value, dict):
            extensions.update(ext_value)
    
    # Then look for individual extension declarations (extensions.X format)
    # These take precedence over any duplicates in the 'extensions' key
    for key, value in header.items():
        if key.startswith('extensions.'):
            prefix = key[len('extensions.'):]
            
            # Ensure the value is properly parsed from JSON if needed
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    # If parsing fails, it's not a valid JSON value, so we keep it as is
                    pass
            
            extensions[prefix] = value
    
    return extensions


def find_extension_keys(header: Dict[str, Any], extensions: Dict[str, str], 
                      namespace_separator: str = DEFAULT_NAMESPACE_SEPARATOR) -> List[str]:
    """
    Find all extension keys in the NRRD header.
    
    Args:
        header: The NRRD header dictionary.
        extensions: Dictionary of extension names to URIs.
        namespace_separator: The separator used between namespace and subkey.
        
    Returns:
        A list of extension keys found in the header.
    """
    extension_keys = []
    
    for key in header.keys():
        if namespace_separator in key:
            prefix, _ = key.split(namespace_separator, 1)
            if prefix in extensions:
                extension_keys.append(key)
    
    return extension_keys


def parse_json_value(value_str: str) -> Any:
    """
    Try to parse a string as JSON, returning the original string if parsing fails.
    
    Args:
        value_str: The string to parse.
        
    Returns:
        The parsed JSON value, or the original string if parsing fails.
    """
    if not isinstance(value_str, str):
        return value_str
        
    try:
        # Try to parse as JSON
        parsed_value = json.loads(value_str)
        
        # If the parsed value is a string itself (happens with quoted strings),
        # strip the extra layer of quotes
        if isinstance(parsed_value, str) and parsed_value.startswith('"') and parsed_value.endswith('"'):
            try:
                parsed_value = json.loads(parsed_value)
            except (json.JSONDecodeError, TypeError):
                pass
                
        return parsed_value
    except (json.JSONDecodeError, TypeError):
        # Return original string if parsing fails
        return value_str


def process_extension_fields(header: Dict[str, Any], 
                           namespace_separator: str = DEFAULT_NAMESPACE_SEPARATOR,
                           parse_json: bool = True) -> Tuple[Dict[str, Any], ExtensionsDict]:
    """
    Process extension fields in the NRRD header into a structured format.
    
    This function:
    1. Extracts extension declarations from the header
    2. Identifies all keys with the extension prefix pattern
    3. Parses their values as JSON if appropriate
    4. Groups them by namespace and reconstructs hierarchical data
    5. Returns both the processed header (without extension fields) and the structured extensions
    
    Args:
        header: The NRRD header dictionary containing extension declarations and fields
        namespace_separator: The separator used between namespace and subkey (default: "/")
        parse_json: Whether to parse extension field values as JSON (default: True)
        
    Returns:
        A tuple of (processed_header, extensions_dict), where:
        - processed_header: Original header without the processed extension fields
        - extensions_dict: Dictionary mapping extension names to objects with "uri" and "data" fields
    
    Example:
        >>> header = {
        ...     'dimension': 3,
        ...     'type': 'float',
        ...     'extensions': '{"meta":"https://example.org/meta/v1.0.0"}',
        ...     'meta/name': '"Dataset"', 
        ...     'meta/keywords': '["tag1", "tag2"]'
        ... }
        >>> processed_header, ext_dict = process_extension_fields(header)
        >>> print(ext_dict['meta']['data']['name'])
        Dataset
        >>> print(ext_dict['meta']['data']['keywords'])
        ['tag1', 'tag2']
    """
    # Make a copy of the header to avoid modifying the original
    processed_header = header.copy()
    
    # Get all extension declarations
    extensions_uris = parse_extensions_from_header(processed_header)
    
    # Extensions must be declared if extension fields are to be processed
    # Note: We don't raise an error anymore as reader.py now handles this with a warning
    
    # Initialize the extensions dictionary with the new structure
    extensions_dict: ExtensionsDict = {}
    for prefix, uri in extensions_uris.items():
        extensions_dict[prefix] = {
            "uri": uri,
            "data": {}
        }
    
    # Remove extension declarations from the header
    # Remove the consolidated 'extensions' key if present
    if 'extensions' in processed_header:
        del processed_header['extensions']
        
    # Remove individual extension.* declarations
    for key in list(extensions_uris.keys()):
        full_key = f'extensions.{key}'
        if full_key in processed_header:
            del processed_header[full_key]
    
    # Find all extension keys
    extension_keys = find_extension_keys(processed_header, extensions_uris, namespace_separator)
    
    # Group extension keys by namespace
    extension_fields = []
    for key in extension_keys:
        value = processed_header[key]
        
        # Parse as JSON if requested
        if parse_json:
            value = parse_json_value(value)
            
        # Add to list of extension fields
        extension_fields.append({key: value})
        
        # Remove from processed header
        del processed_header[key]
    
    # Reconstitute extension data
    extension_data = reconstitute_namespaces(
        extension_fields, 
        namespace_separator=namespace_separator, 
        namespace_list=list(extensions_uris.keys())
    )
    
    # Place the reconstituted data into the new extensions structure
    for prefix, data in extension_data.items():
        if prefix in extensions_dict:
            extensions_dict[prefix]["data"] = data
    
    return processed_header, extensions_dict


def prepare_extensions_for_writing(extensions_dict: ExtensionsDict, 
                                  max_length: int = DEFAULT_MAX_LINE_LENGTH,
                                  namespace_separator: str = DEFAULT_NAMESPACE_SEPARATOR,
                                  flatten: FlattenMode = "auto") -> Dict[str, str]:
    """
    Prepare extensions data for writing to a NRRD file.
    
    This function converts the structured extensions dictionary into a flat dictionary
    of key-value pairs suitable for writing to a NRRD header file. The nested structures
    are either kept intact or flattened according to the flatten parameter.
    
    Args:
        extensions_dict: Dictionary mapping extension names to objects with "uri" and "data" fields.
            Each extension object must have the format {'uri': str, 'data': dict}.
        max_length: Maximum line length for auto-flattening mode (default: 78 characters).
        namespace_separator: The separator used between namespace and subkey (default: "/").
        flatten: Controls how hierarchical data is flattened:
            - "auto": Only flatten nested structures if the serialized length exceeds max_length
            - "always": Always flatten all nested objects/arrays into separate key-value pairs
            - "never": Never flatten, keeping nested structures as JSON objects
        
    Returns:
        A dictionary of key-value pairs to include in the NRRD header.
        Values are pre-serialized to JSON strings ready to be written.
    
    Example:
        >>> extensions = {
        ...     'meta': {
        ...         'uri': 'https://example.org/meta/v1.0.0',
        ...         'data': {
        ...             'name': 'Dataset',
        ...             'creator': {'name': 'John', 'org': 'Example'}
        ...         }
        ...     }
        ... }
        >>> # With auto-flattening
        >>> result = prepare_extensions_for_writing(extensions)
        >>> # Result will include:
        >>> # 'extensions.meta': '"https://example.org/meta/v1.0.0"'
        >>> # 'meta/name': '"Dataset"'
        >>> # 'meta/creator': '{"name":"John","org":"Example"}'
        >>> 
        >>> # With always-flattening
        >>> result = prepare_extensions_for_writing(extensions, flatten='always')
        >>> # Result will include:
        >>> # 'extensions.meta': '"https://example.org/meta/v1.0.0"'
        >>> # 'meta/name': '"Dataset"'
        >>> # 'meta/creator.name': '"John"'
        >>> # 'meta/creator.org': '"Example"'
    """
    result = {}
    
    # Extract extensions and extension_data from the new structure
    extensions = {}
    extension_data = {}
    
    for prefix, ext_obj in extensions_dict.items():
        # Get URI, defaulting to empty string if not present
        uri = ext_obj.get("uri", "")
        extensions[prefix] = uri
        
        # Get data
        data = ext_obj.get("data", {})
        if data:  # Only add if there's actual data
            extension_data[prefix] = data
    
    # Add extension declarations
    for prefix, uri in extensions.items():
        result[f'extensions.{prefix}'] = serialize_nrrd_json(uri)
    
    # Define a custom serializer function for line length calculation
    def calc_line_length(obj):
        if not isinstance(obj, dict):
            return json.dumps(obj)
        
        serialized = json.dumps(obj, separators=JSON_SEPARATORS)
        
        if len(obj) == 1:
            key, _ = next(iter(obj.items()))
            serialized = f"{key}:={serialized}"
            
        return serialized
    
    # Flatten extension data
    flattened_fields = flatten_namespaces(
        extension_data,
        namespace_separator=namespace_separator,
        flatten=flatten,
        max_length=max_length,
        serializer=calc_line_length
    )
    
    # Add flattened fields to result
    for field_dict in flattened_fields:
        for key, value in field_dict.items():
            # Serialize values to JSON
            result[key] = serialize_nrrd_json(value)
    
    return result


def get_field_type_extension(field: str, extensions: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Determine the field type for an extension field.
    
    Args:
        field: The field name.
        extensions: Dictionary of extension names to URIs.
        
    Returns:
        Field type if it's an extension field, None otherwise.
    """
    # Handle extension declarations (both single and dot notation)
    if field == 'extensions' or field.startswith('extensions.'):
        return 'json'
    
    # Handle extension fields
    if extensions and '/' in field:
        prefix, _ = field.split('/', 1)
        if prefix in extensions:
            return 'json'
            
    return None


def serialize_nrrd_json(value: Any) -> str:
    """
    Serialize a value to a JSON string with consistent formatting.
    
    This centralizes JSON serialization for NRRD extensions to ensure
    consistent formatting across all serialized values.
    
    Args:
        value: The value to serialize to JSON.
        
    Returns:
        A JSON-formatted string.
    """
    return json.dumps(value, separators=JSON_SEPARATORS)


def parse_json_nrrd(value: str) -> Any:
    """
    Parse a JSON value from a NRRD file.
    
    This function is used for handling json field types in NRRD.
    
    Args:
        value: The string value to parse.
        
    Returns:
        The parsed JSON value or original value if parsing fails.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        # If it's not valid JSON, return as is
        return value
        
        
def reconstruct_hierarchy(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    A convenience wrapper for reconstitute that takes a dict and 
    converts it to the expected format.
    
    Args:
        data: Dictionary of flattened fields.
        
    Returns:
        A hierarchical structure.
    """
    # Convert dict to list of single-item dicts
    flattened_list = [{k: v} for k, v in data.items()]
    
    # Use reconstitute to rebuild the hierarchy
    return reconstitute(flattened_list)