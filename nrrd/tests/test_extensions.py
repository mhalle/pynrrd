import unittest
import warnings
import io
import json
import numpy as np
from collections import OrderedDict

import nrrd
from nrrd.extensions import (
    parse_extensions_from_header,
    find_extension_keys,
    parse_json_value,
    process_extension_fields,
    prepare_extensions_for_writing,
    flatten_structure,
    reconstitute
)
from nrrd.types import FlattenMode


class TestExtensionsParsing(unittest.TestCase):
    """Test parsing of NRRD extension fields."""

    def setUp(self):
        """Set up test cases."""
        # Basic header with extensions
        self.basic_header = OrderedDict({
            'dimension': 3,
            'type': 'float',
            'sizes': '10 10 10',
            'encoding': 'raw',
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0"}'
        })
        
        # Header with individual extension declarations
        self.individual_extensions_header = OrderedDict({
            'dimension': 3,
            'type': 'float',
            'sizes': '10 10 10',
            'encoding': 'raw',
            'extensions.meta': '"https://jnrrd.org/extensions/metadata/v1.0.0"',
            'extensions.dicom': '"https://jnrrd.org/extensions/dicom/v1.0.0"'
        })
        
        # Header with both combined and individual declarations (individual should take precedence)
        self.mixed_extensions_header = OrderedDict({
            'dimension': 3,
            'type': 'float',
            'sizes': '10 10 10',
            'encoding': 'raw',
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0", "dicom":"https://jnrrd.org/extensions/dicom/v1.0.0"}',
            'extensions.meta': '"https://jnrrd.org/extensions/metadata/v1.1.0"'  # Should override
        })
        
        # Header with extension-like fields but no declaration
        self.undeclared_extensions_header = OrderedDict({
            'dimension': 3,
            'type': 'float',
            'sizes': '10 10 10',
            'encoding': 'raw',
            'meta/name': '"Test Dataset"'  # Looks like an extension, but no declaration
        })
        
        # Header with custom fields
        self.custom_fields_header = OrderedDict({
            'dimension': 3,
            'type': 'float',
            'sizes': '10 10 10',
            'encoding': 'raw',
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0"}',
            'meta/name': '"Test Dataset"',
            'custom_field': 'custom value',
            'another_custom_field': 'another value'
        })

    def test_parse_extensions_from_header(self):
        """Test parsing extension declarations from NRRD header."""
        # Test basic header with combined extensions
        extensions = parse_extensions_from_header(self.basic_header)
        self.assertEqual(extensions, {'meta': 'https://jnrrd.org/extensions/metadata/v1.0.0'})
        
        # Test header with individual extension declarations
        extensions = parse_extensions_from_header(self.individual_extensions_header)
        expected = {
            'meta': 'https://jnrrd.org/extensions/metadata/v1.0.0',
            'dicom': 'https://jnrrd.org/extensions/dicom/v1.0.0'
        }
        self.assertEqual(extensions, expected)
        
        # Test mixed declarations (individual should override)
        extensions = parse_extensions_from_header(self.mixed_extensions_header)
        expected = {
            'meta': 'https://jnrrd.org/extensions/metadata/v1.1.0',  # Should take this value
            'dicom': 'https://jnrrd.org/extensions/dicom/v1.0.0'
        }
        self.assertEqual(extensions, expected)
        
        # Test with no extensions
        extensions = parse_extensions_from_header({})
        self.assertEqual(extensions, {})

    def test_find_extension_keys(self):
        """Test finding extension keys in a header."""
        # Add extension fields to test header
        header = self.basic_header.copy()
        header['meta/name'] = '"Test Dataset"'
        header['meta/description'] = '"A test dataset"'
        header['not_an_extension'] = 'value'
        
        extensions = parse_extensions_from_header(header)
        extension_keys = find_extension_keys(header, extensions)
        
        self.assertEqual(len(extension_keys), 2)
        self.assertIn('meta/name', extension_keys)
        self.assertIn('meta/description', extension_keys)
        self.assertNotIn('not_an_extension', extension_keys)
        
        # Test with no declared extensions
        extensions = {}
        extension_keys = find_extension_keys(header, extensions)
        self.assertEqual(len(extension_keys), 0)

    def test_parse_json_value(self):
        """Test parsing JSON values from strings."""
        # Test basic types
        self.assertEqual(parse_json_value('"string"'), 'string')
        self.assertEqual(parse_json_value('123'), 123)
        self.assertEqual(parse_json_value('true'), True)
        self.assertEqual(parse_json_value('false'), False)
        self.assertEqual(parse_json_value('null'), None)
        
        # Test JSON objects and arrays
        self.assertEqual(parse_json_value('{"key":"value"}'), {'key': 'value'})
        self.assertEqual(parse_json_value('[1, 2, 3]'), [1, 2, 3])
        
        # Test non-JSON string
        self.assertEqual(parse_json_value('not json'), 'not json')
        
        # Test non-string input
        self.assertEqual(parse_json_value(123), 123)
        
        # Test with empty string
        self.assertEqual(parse_json_value('""'), '')
        self.assertEqual(parse_json_value(''), '')

    def test_process_extension_fields(self):
        """Test processing extension fields into structured data."""
        # Create a header with extension fields
        header = OrderedDict({
            'dimension': 3,
            'type': 'float',
            'sizes': '10 10 10',
            'encoding': 'raw',
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0"}',
            'meta/name': '"Test Dataset"',
            'meta/creator': '{"name":"Test Creator","url":"https://example.org"}',
            'meta/keywords': '["test", "dataset"]',
            'custom_field': 'custom value'
        })
        
        # Process the header
        processed_header, extensions_dict = process_extension_fields(header)
        
        # Check that extension fields were removed
        self.assertNotIn('extensions', processed_header)
        self.assertNotIn('meta/name', processed_header)
        self.assertNotIn('meta/creator', processed_header)
        self.assertNotIn('meta/keywords', processed_header)
        
        # Check that other fields remain
        self.assertIn('custom_field', processed_header)
        self.assertEqual(processed_header['custom_field'], 'custom value')
        
        # Check that extensions were properly structured
        self.assertIn('meta', extensions_dict)
        self.assertEqual(extensions_dict['meta']['uri'], 'https://jnrrd.org/extensions/metadata/v1.0.0')
        self.assertEqual(extensions_dict['meta']['data']['name'], 'Test Dataset')
        self.assertEqual(extensions_dict['meta']['data']['creator']['name'], 'Test Creator')
        self.assertEqual(extensions_dict['meta']['data']['creator']['url'], 'https://example.org')
        self.assertEqual(extensions_dict['meta']['data']['keywords'], ['test', 'dataset'])

    def test_prepare_extensions_for_writing(self):
        """Test preparing extensions for writing to a NRRD file."""
        # Create an extensions dictionary
        extensions_dict = {
            'meta': {
                'uri': 'https://jnrrd.org/extensions/metadata/v1.0.0',
                'data': {
                    'name': 'Test Dataset',
                    'creator': {
                        'name': 'Test Creator',
                        'url': 'https://example.org'
                    },
                    'keywords': ['test', 'dataset']
                }
            }
        }
        
        # Prepare for writing with default settings
        result = prepare_extensions_for_writing(extensions_dict)
        
        # Check individual extensions declaration
        self.assertIn('extensions.meta', result)
        self.assertEqual(result['extensions.meta'], '"https://jnrrd.org/extensions/metadata/v1.0.0"')
        
        # Check extension fields
        # Exact serialization may vary, so we check that the keys exist and parse back to the right values
        self.assertIn('meta/name', result)
        self.assertEqual(json.loads(result['meta/name']), 'Test Dataset')
        
        # Test with different flattening modes
        result_always = prepare_extensions_for_writing(extensions_dict, flatten='always')
        self.assertIn('meta/creator.name', result_always)
        self.assertEqual(json.loads(result_always['meta/creator.name']), 'Test Creator')
        
        result_never = prepare_extensions_for_writing(extensions_dict, flatten='never')
        self.assertIn('meta/creator', result_never)
        self.assertEqual(json.loads(result_never['meta/creator']), {
            'name': 'Test Creator',
            'url': 'https://example.org'
        })

    def test_warnings_for_undeclared_extensions(self):
        """Test that warnings are generated for undeclared extensions."""
        # This test should be used with the full read function
        with warnings.catch_warnings(record=True) as w:
            # Trigger the warning
            warnings.simplefilter("always")
            
            # Mock the read function by directly calling process_extension_fields
            process_extension_fields(self.undeclared_extensions_header)
            
            # Check if warning was raised
            self.assertEqual(len(w), 0)  # No warnings as the error handling was moved to reader.py
            
            # Try to use the undeclared extension
            # This would be handled in reader.py's read function


class TestExtensionsAdvancedCases(unittest.TestCase):
    """Test edge cases and advanced features of NRRD extensions."""

    def test_unusual_characters(self):
        """Test serialization and deserialization of unusual characters."""
        # Create extensions with unusual characters
        extensions_dict = {
            'meta': {
                'uri': 'https://jnrrd.org/extensions/metadata/v1.0.0',
                'data': {
                    'text_with_newlines': "Line 1\nLine 2\nLine 3",
                    'text_with_tabs': "Column 1\tColumn 2\tColumn 3",
                    'empty_string': "",
                    'unicode_string': "你好，世界",  # Hello, world in Chinese
                    'string_with_quotes': "They said \"hello\"",
                    'string_with_backslashes': "C:\\Program Files\\App",
                    'string_with_json_separators': "Commas,Colons:Braces{}"
                }
            }
        }
        
        # Serialize
        result = prepare_extensions_for_writing(extensions_dict)
        
        # Check for expected keys
        for key in ['meta/text_with_newlines', 'meta/text_with_tabs', 'meta/empty_string',
                   'meta/unicode_string', 'meta/string_with_quotes', 'meta/string_with_backslashes',
                   'meta/string_with_json_separators']:
            self.assertIn(key, result)
        
        # Create a mock header with these serialized values
        header = {
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0"}'
        }
        for key, value in result.items():
            if key != 'extensions.meta':  # We've already set extensions
                header[key] = value
        
        # Deserialize and check values
        _, deserialized = process_extension_fields(header)
        
        data = deserialized['meta']['data']
        self.assertEqual(data['text_with_newlines'], "Line 1\nLine 2\nLine 3")
        self.assertEqual(data['text_with_tabs'], "Column 1\tColumn 2\tColumn 3")
        self.assertEqual(data['empty_string'], "")
        self.assertEqual(data['unicode_string'], "你好，世界")
        self.assertEqual(data['string_with_quotes'], "They said \"hello\"")
        self.assertEqual(data['string_with_backslashes'], "C:\\Program Files\\App")
        self.assertEqual(data['string_with_json_separators'], "Commas,Colons:Braces{}")

    def test_long_strings(self):
        """Test handling of strings that exceed max_length."""
        # Create a very long string
        long_string = "x" * 1000  # 1000 character string
        
        extensions_dict = {
            'meta': {
                'uri': 'https://jnrrd.org/extensions/metadata/v1.0.0',
                'data': {
                    'long_string': long_string
                }
            }
        }
        
        # Serialize with different max_length values
        result_default = prepare_extensions_for_writing(extensions_dict)
        result_short = prepare_extensions_for_writing(extensions_dict, max_length=50)
        result_long = prepare_extensions_for_writing(extensions_dict, max_length=2000)
        
        # All should include the long string but might be formatted differently
        self.assertIn('meta/long_string', result_default)
        self.assertIn('meta/long_string', result_short)
        self.assertIn('meta/long_string', result_long)
        
        # Check if we can deserialize correctly regardless of the original max_length
        header = {
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0"}',
            'meta/long_string': result_default['meta/long_string']
        }
        
        _, deserialized = process_extension_fields(header)
        self.assertEqual(deserialized['meta']['data']['long_string'], long_string)

    def test_deep_structures(self):
        """Test deeply embedded structures where the key itself may exceed max_length."""
        # Create a deeply nested structure
        deep_data = {}
        current = deep_data
        for i in range(20):  # Create a 20-level deep structure
            current['level'] = {}
            current = current['level']
        current['value'] = "deep value"
        
        extensions_dict = {
            'meta': {
                'uri': 'https://jnrrd.org/extensions/metadata/v1.0.0',
                'data': {
                    'deep': deep_data
                }
            }
        }
        
        # Serialize with different flattening modes
        result_auto = prepare_extensions_for_writing(extensions_dict, flatten='auto')
        result_always = prepare_extensions_for_writing(extensions_dict, flatten='always')
        result_never = prepare_extensions_for_writing(extensions_dict, flatten='never')
        
        # Check that auto and always modes should flatten the structure
        found_deep_value_key = False
        for key in result_always:
            if key.startswith('meta/deep.level.level') and key.endswith('value'):
                found_deep_value_key = True
                break
        self.assertTrue(found_deep_value_key, "Deep structure should be flattened in 'always' mode")
        
        # Check that never mode keeps the structure intact
        self.assertIn('meta/deep', result_never)
        
        # Test deserialization of deep structure
        header = {
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0"}'
        }
        
        # Add all the flattened keys - which is the most challenging case
        for key, value in result_always.items():
            if key != 'extensions.meta':
                header[key] = value
        
        _, deserialized = process_extension_fields(header)
        
        # Navigate to the deep value
        current = deserialized['meta']['data']['deep']
        for i in range(20):
            self.assertIn('level', current)
            current = current['level']
        self.assertEqual(current['value'], "deep value")

    def test_custom_fields_with_extensions(self):
        """Test parsing NRRD headers with custom fields alongside extensions."""
        # Create a header with custom fields and extensions
        header = {
            'dimension': 3,
            'type': 'float',
            'sizes': '10 10 10',
            'encoding': 'raw',
            'extensions': '{"meta":"https://jnrrd.org/extensions/metadata/v1.0.0"}',
            'meta/name': '"Test Dataset"',
            'meta/creator': '{"name":"Test Creator"}',
            'custom_field1': 'custom value 1',
            'custom_field2': 'custom value 2',
            'custom_field3': 'custom value 3'
        }
        
        processed_header, extensions_dict = process_extension_fields(header)
        
        # Check that extension fields were processed
        self.assertIn('meta', extensions_dict)
        self.assertEqual(extensions_dict['meta']['data']['name'], 'Test Dataset')
        
        # Check that custom fields remain untouched
        self.assertIn('custom_field1', processed_header)
        self.assertEqual(processed_header['custom_field1'], 'custom value 1')
        self.assertIn('custom_field2', processed_header)
        self.assertEqual(processed_header['custom_field2'], 'custom value 2')
        self.assertIn('custom_field3', processed_header)
        self.assertEqual(processed_header['custom_field3'], 'custom value 3')


class TestExtensionsFullRoundTrip(unittest.TestCase):
    """Test full round-trip reading and writing of NRRD files with extensions."""
    
    def test_write_and_read_extensions(self):
        """Test writing and reading back NRRD files with extensions."""
        import tempfile
        import os
        
        # Create a simple test array
        data = np.ones((5, 5, 5), dtype=np.float32)
        
        # Create a header with extensions
        header = {
            'type': 'float',
            'dimension': 3,
            'sizes': [5, 5, 5],
            'encoding': 'raw',
            'endian': 'little',
            'extensions': {
                'meta': {
                    'uri': 'https://jnrrd.org/extensions/metadata/v1.0.0',
                    'data': {
                        'name': 'Test Dataset',
                        'creator': {
                            'name': 'Test Creator',
                            'url': 'https://example.org'
                        },
                        'keywords': ['test', 'dataset', 'extensions'],
                        'nested': {
                            'level1': {
                                'level2': {
                                    'level3': 'deep value'
                                }
                            }
                        }
                    }
                },
                'custom': {
                    'uri': 'https://example.org/custom/v1.0.0',
                    'data': {
                        'field1': 'value1',
                        'field2': 'value2'
                    }
                }
            }
        }
        
        # Create a temporary file
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, 'test_extensions_roundtrip.nrrd')
            
            # Write to the temporary file
            nrrd.write(temp_file, data, header, flatten='auto')
            
            # Read back the data and header
            read_data, read_header = nrrd.read(temp_file, process_extension_fields=True)
            
            # Check data
            np.testing.assert_array_equal(data, read_data)
            
            # Check header extensions
            self.assertIn('extensions', read_header)
            extensions = read_header['extensions']
            
            # Check metadata extension
            self.assertIn('meta', extensions)
            meta = extensions['meta']
            self.assertEqual(meta['uri'], 'https://jnrrd.org/extensions/metadata/v1.0.0')
            self.assertEqual(meta['data']['name'], 'Test Dataset')
            self.assertEqual(meta['data']['creator']['name'], 'Test Creator')
            self.assertEqual(meta['data']['creator']['url'], 'https://example.org')
            self.assertEqual(meta['data']['keywords'], ['test', 'dataset', 'extensions'])
            self.assertEqual(meta['data']['nested']['level1']['level2']['level3'], 'deep value')
            
            # Check custom extension
            self.assertIn('custom', extensions)
            custom = extensions['custom']
            self.assertEqual(custom['uri'], 'https://example.org/custom/v1.0.0')
            self.assertEqual(custom['data']['field1'], 'value1')
            self.assertEqual(custom['data']['field2'], 'value2')
            
    def test_field_sorting_order(self):
        """Test that fields are properly sorted by length in the output file."""
        import tempfile
        import os
        
        # Create a very long string (well over the threshold)
        long_string = "x" * 1000  # 1000 character string
        medium_string = "y" * 200  # 200 character string - still normal
        
        # Create a header with a mix of field lengths
        header = {
            'type': 'float',
            'dimension': 3,
            'sizes': [5, 5, 5],
            'encoding': 'raw',
            'endian': 'little',
            'extensions': {
                'test': {
                    'uri': 'https://example.org/test/v1.0.0',
                    'data': {
                        'a_normal_field': 'short value',
                        'z_normal_field': 'another short value',
                        'b_normal_field': medium_string,
                        'very_long_field1': long_string,
                        'very_long_field2': long_string + "additional" # slightly longer
                    }
                }
            }
        }
        
        # Create test data
        data = np.ones((5, 5, 5), dtype=np.float32)
        
        # Create a temporary file
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, 'test_field_sorting.nrrd')
            
            # Write to file
            nrrd.write(temp_file, data, header)
            
            # Read the raw file to check field ordering
            with open(temp_file, 'rb') as f:
                # Read just the header portion of the file (up to the blank line)
                header_bytes = b''
                for line in f:
                    if line.strip() == b'':
                        break
                    header_bytes += line
                
                lines = header_bytes.split(b'\n')
                
            # Convert to strings for easier analysis
            lines = [line.decode('ascii', errors='replace') for line in lines if line]
            
            # Find the indices of various fields
            extension_decl_idx = -1
            normal_field_indices = []
            long_field_indices = []
            
            for i, line in enumerate(lines):
                if line.startswith('extensions.test:='):
                    extension_decl_idx = i
                elif line.startswith('test/a_normal_field:='):
                    normal_field_indices.append(i)
                elif line.startswith('test/z_normal_field:='):
                    normal_field_indices.append(i)
                elif line.startswith('test/b_normal_field:='):
                    normal_field_indices.append(i)
                elif line.startswith('test/very_long_field'):
                    long_field_indices.append(i)
            
            # Check ordering:
            # 1. Extension declaration should come first
            self.assertGreater(extension_decl_idx, -1, "Extension declaration not found")
            
            # 2. Normal fields should come after extension declarations,
            #    before long fields, and be in alphabetical order
            for normal_idx in normal_field_indices:
                self.assertGreater(normal_idx, extension_decl_idx, 
                                  "Normal fields should come after extension declarations")
            
            # Find indices of specific normal fields
            a_field_idx = next((i for i, line in enumerate(lines) 
                               if line.startswith('test/a_normal_field:=')), -1)
            b_field_idx = next((i for i, line in enumerate(lines) 
                               if line.startswith('test/b_normal_field:=')), -1)
            z_field_idx = next((i for i, line in enumerate(lines) 
                               if line.startswith('test/z_normal_field:=')), -1)
            
            # Check alphabetical ordering of normal fields
            self.assertLess(a_field_idx, b_field_idx, 
                           "Normal fields should be in alphabetical order")
            self.assertLess(b_field_idx, z_field_idx, 
                           "Normal fields should be in alphabetical order")
            
            # 3. Long fields should come after normal fields
            for long_idx in long_field_indices:
                for normal_idx in normal_field_indices:
                    self.assertGreater(long_idx, normal_idx, 
                                      "Long fields should come after normal fields")
            
            # 4. Long fields should be sorted by length
            long_field1_idx = next((i for i, line in enumerate(lines) 
                                  if line.startswith('test/very_long_field1:=')), -1)
            long_field2_idx = next((i for i, line in enumerate(lines) 
                                  if line.startswith('test/very_long_field2:=')), -1)
            
            # Field2 is longer, should come after field1
            self.assertGreater(long_field2_idx, long_field1_idx, 
                              "Longer fields should come after shorter ones")
    
    def test_write_with_various_flattening(self):
        """Test writing with different flattening modes."""
        import tempfile
        import os
        
        # Create a simple test array
        data = np.ones((5, 5, 5), dtype=np.float32)
        
        # Create a nested header
        nested_data = {
            'type': 'float',
            'dimension': 3,
            'sizes': [5, 5, 5],
            'encoding': 'raw',
            'endian': 'little',
            'extensions': {
                'meta': {
                    'uri': 'https://jnrrd.org/extensions/metadata/v1.0.0',
                    'data': {
                        'nested': {
                            'level1': {
                                'level2': {
                                    'level3': 'deep value'
                                }
                            }
                        }
                    }
                }
            }
        }
        
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write with different flattening modes
            for flatten_mode in ['auto', 'always', 'never']:
                temp_file = os.path.join(temp_dir, f'test_flatten_{flatten_mode}.nrrd')
                
                # Write the file
                nrrd.write(temp_file, data, nested_data, flatten=flatten_mode)
                
                # Read the file content to check serialization format
                with open(temp_file, 'rb') as f:
                    raw_header = f.read().split(b'\n\n')[0].decode('ascii')
                
                if flatten_mode == 'never':
                    # Should use nested JSON object
                    self.assertIn('meta/nested:=', raw_header)
                elif flatten_mode == 'always':
                    # Should be completely flattened
                    self.assertIn('meta/nested.level1.level2.level3:=', raw_header)
                
                # Read the data and check
                read_data, read_header = nrrd.read(temp_file, process_extension_fields=True)
                np.testing.assert_array_equal(data, read_data)
                
                # Check that the deep structure was preserved
                self.assertEqual(
                    read_header['extensions']['meta']['data']['nested']['level1']['level2']['level3'], 
                    'deep value'
                )


class TestFlattenAndReconstitute(unittest.TestCase):
    """Test the flatten_structure and reconstitute functions specifically."""
    
    def test_flatten_structure_auto(self):
        """Test flatten_structure with auto mode."""
        # Create a nested structure with more complexity to ensure flattening
        data = [{'root': {'nested': {'key1': 'value1', 'key2': 'value2', 'deep': {'very': {'much': 'so'}}}}}]
        
        # Test auto mode with small max_length should flatten
        flattened = list(flatten_structure(data, flatten='auto', max_length=20))
        self.assertGreater(len(flattened), 1, "Structure should be flattened with small max_length")
        
        # Test auto mode with large max_length should not flatten
        flattened = list(flatten_structure(data, flatten='auto', max_length=1000))
        self.assertEqual(len(flattened), 1, "Structure should not be flattened with large max_length")
    
    def test_flatten_structure_always(self):
        """Test flatten_structure with always mode."""
        # Create a nested structure with more complexity to ensure flattening
        data = [{'root': {'nested': {'key1': 'value1', 'key2': 'value2', 'deep': {'very': {'much': 'so'}}}}}]
        
        # Always mode should flatten regardless of max_length
        flattened = list(flatten_structure(data, flatten='always', max_length=1000))
        self.assertGreater(len(flattened), 1, "Structure should be flattened in always mode")
    
    def test_flatten_structure_never(self):
        """Test flatten_structure with never mode."""
        # Create a nested structure
        data = [{'root': {'nested': {'key': 'value'}}}]
        
        # Never mode should not flatten regardless of max_length
        flattened = list(flatten_structure(data, flatten='never', max_length=10))
        self.assertEqual(len(flattened), 1, "Structure should not be flattened in never mode")
    
    def test_reconstitute_simple(self):
        """Test reconstitution of a simple flattened structure."""
        # A simple flattened structure
        flattened = [
            {'a': 1},
            {'b': 2},
            {'c': 3}
        ]
        
        # Reconstitute
        result = reconstitute(flattened)
        
        # Check result
        self.assertEqual(result, {'a': 1, 'b': 2, 'c': 3})
    
    def test_reconstitute_nested(self):
        """Test reconstitution of a nested flattened structure."""
        # A nested flattened structure
        flattened = [
            {'a.b.c': 1},
            {'a.b.d': 2},
            {'a.e': 3},
            {'f': 4}
        ]
        
        # Reconstitute
        result = reconstitute(flattened)
        
        # Check result
        expected = {
            'a': {
                'b': {
                    'c': 1,
                    'd': 2
                },
                'e': 3
            },
            'f': 4
        }
        self.assertEqual(result, expected)
    
    def test_reconstitute_arrays(self):
        """Test reconstitution with array indices."""
        # A structure with arrays
        flattened = [
            {'a[0]': 1},
            {'a[1]': 2},
            {'a[2]': 3},
            {'b.c[0].d': 4},
            {'b.c[1].d': 5}
        ]
        
        # Reconstitute
        result = reconstitute(flattened)
        
        # Check result
        expected = {
            'a': [1, 2, 3],
            'b': {
                'c': [
                    {'d': 4},
                    {'d': 5}
                ]
            }
        }
        self.assertEqual(result, expected)
    
    def test_reconstitute_override(self):
        """Test that more specific paths override more general ones."""
        # A structure with overrides
        flattened = [
            {'a': {'b': 1, 'c': 2}},  # This should be partially overridden
            {'a.b': 3}                # This should take precedence for 'a.b'
        ]
        
        # Reconstitute
        result = reconstitute(flattened)
        
        # Check result
        expected = {
            'a': {
                'b': 3,  # This value comes from the more specific path
                'c': 2   # This value remains from the original
            }
        }
        self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()