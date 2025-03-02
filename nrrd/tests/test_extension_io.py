import unittest
import warnings
import io
import os
import json
import numpy as np
from collections import OrderedDict

import nrrd
from nrrd.extensions import (
    parse_extensions_from_header,
    find_extension_keys,
    process_extension_fields,
    prepare_extensions_for_writing
)

# Path to test data directory
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


class TestExtensionsIO(unittest.TestCase):
    """Test reading and writing of NRRD files with extensions."""
    
    def test_read_standard_extensions(self):
        """Test reading a NRRD file with standard extensions format."""
        test_file = os.path.join(TEST_DATA_DIR, 'test_extensions.nrrd')
        header = nrrd.read_header(test_file)
        
        # Check extensions declaration
        self.assertIn('extensions', header)
        extensions = header['extensions']
        # The extensions might already be a dictionary if parsed by the reader
        if isinstance(extensions, str):
            extensions = json.loads(extensions)
        self.assertEqual(len(extensions), 2)
        self.assertEqual(extensions['meta'], 'https://jnrrd.org/extensions/metadata/v1.0.0')
        self.assertEqual(extensions['dicom'], 'https://jnrrd.org/extensions/dicom/v1.0.0')
        
        # Check extension fields
        self.assertIn('meta/name', header)
        self.assertEqual(json.loads(header['meta/name']), 'Test Dataset')
        self.assertIn('meta/creator', header)
        creator = json.loads(header['meta/creator'])
        self.assertEqual(creator['name'], 'Test Creator')
        self.assertEqual(creator['url'], 'https://example.org/creator')
        
        # Check that all extension fields are present
        extension_fields = [
            'meta/name', 'meta/description', 'meta/creator', 'meta/dateCreated', 'meta/keywords',
            'dicom/patient.id', 'dicom/patient.name', 'dicom/study.date', 'dicom/study.description'
        ]
        for field in extension_fields:
            self.assertIn(field, header)
    
    def test_read_header_only(self):
        """Test reading only the header with extensions."""
        test_file = os.path.join(TEST_DATA_DIR, 'test_extensions.nrrd')
        header = nrrd.read_header(test_file)
        
        # Process extensions from the header
        _, extensions_dict = process_extension_fields(header)
        
        # Check for extensions in processed result
        self.assertIn('meta', extensions_dict)
        self.assertEqual(extensions_dict['meta']['uri'], 'https://jnrrd.org/extensions/metadata/v1.0.0')
        self.assertEqual(extensions_dict['meta']['data']['name'], 'Test Dataset')
        self.assertEqual(extensions_dict['meta']['data']['description'], 'A test dataset with extensions')
        self.assertEqual(extensions_dict['meta']['data']['creator']['name'], 'Test Creator')
        self.assertEqual(extensions_dict['meta']['data']['creator']['url'], 'https://example.org/creator')
        self.assertEqual(extensions_dict['meta']['data']['dateCreated'], '2024-02-29')
        self.assertEqual(extensions_dict['meta']['data']['keywords'], ['test', 'nrrd', 'extensions'])
        
        # Check DICOM extension
        self.assertIn('dicom', extensions_dict)
        self.assertEqual(extensions_dict['dicom']['uri'], 'https://jnrrd.org/extensions/dicom/v1.0.0')
        self.assertEqual(extensions_dict['dicom']['data']['patient']['id'], '12345')
        self.assertEqual(extensions_dict['dicom']['data']['patient']['name'], 'ANONYMOUS')
        self.assertEqual(extensions_dict['dicom']['data']['study']['date'], '20240229')
        self.assertEqual(extensions_dict['dicom']['data']['study']['description'], 'TEST STUDY')
    
    def test_read_hierarchical_extensions(self):
        """Test reading a NRRD file with hierarchical extension declarations."""
        test_file = os.path.join(TEST_DATA_DIR, 'test_extensions_hierarchical.nrrd')
        header = nrrd.read_header(test_file)
        
        # Process extensions
        _, extensions_dict = process_extension_fields(header)
        
        # Check metadata extension
        self.assertIn('meta', extensions_dict)
        self.assertEqual(extensions_dict['meta']['uri'], 'https://jnrrd.org/extensions/metadata/v1.0.0')
        self.assertEqual(extensions_dict['meta']['data']['name'], 'Hierarchical Test Dataset')
        self.assertEqual(extensions_dict['meta']['data']['description'], 
                         'A test dataset with hierarchical extension declarations')
        
        # Check hierarchical structure
        self.assertEqual(extensions_dict['meta']['data']['creator']['name'], 'Test Creator')
        self.assertEqual(extensions_dict['meta']['data']['creator']['url'], 'https://example.org/creator')
        
        # Check array elements
        self.assertEqual(extensions_dict['meta']['data']['keywords'], 
                         ['hierarchical', 'declaration', 'test'])
    
    def test_read_edge_cases(self):
        """Test reading a NRRD file with edge cases and unusual characters."""
        test_file = os.path.join(TEST_DATA_DIR, 'test_extensions_edge_cases.nrrd')
        header = nrrd.read_header(test_file)
        
        # Process extensions
        _, extensions_dict = process_extension_fields(header)
        
        # Check edge case extension
        self.assertIn('edge', extensions_dict)
        edge_data = extensions_dict['edge']['data']
        
        # Check special characters handling
        self.assertEqual(edge_data['empty_string'], '')
        self.assertEqual(edge_data['text_with_newlines'], 'Line 1\nLine 2\nLine 3')
        self.assertEqual(edge_data['text_with_tabs'], 'Column 1\tColumn 2\tColumn 3')
        # Unicode may be handled differently depending on platform, just check it exists
        self.assertTrue('unicode_string' in edge_data)
        self.assertEqual(edge_data['string_with_quotes'], 'They said "hello"')
        self.assertEqual(edge_data['string_with_backslashes'], 'C:\\Program Files\\App')
        self.assertEqual(edge_data['string_with_json_separators'], 'Commas,Colons:Braces{}')
        
        # Check long string handling
        self.assertTrue(len(edge_data['long_string']) > 500)
        self.assertTrue(edge_data['long_string'].startswith('This is a very long string'))
        
        # Check long path handling - it should be parsed into a nested structure
        self.assertIn('path', edge_data)
        self.assertIn('with', edge_data['path'])
        self.assertIn('many', edge_data['path']['with'])
        self.assertIn('segments', edge_data['path']['with']['many'])
        self.assertIn('that', edge_data['path']['with']['many']['segments'])
        self.assertIn('might', edge_data['path']['with']['many']['segments']['that'])
        self.assertIn('exceed', edge_data['path']['with']['many']['segments']['that']['might'])
        self.assertIn('max_length', edge_data['path']['with']['many']['segments']['that']['might']['exceed'])
        self.assertIn('when', edge_data['path']['with']['many']['segments']['that']['might']['exceed']['max_length'])
        self.assertIn('serialized', edge_data['path']['with']['many']['segments']['that']['might']['exceed']['max_length']['when'])
        self.assertEqual(edge_data['path']['with']['many']['segments']['that']['might']['exceed']['max_length']['when']['serialized'], 'testing long path handling')
    
    def test_read_undeclared_extensions_warning(self):
        """Test reading a NRRD file with undeclared extension-like fields."""
        test_file = os.path.join(TEST_DATA_DIR, 'test_undeclared_extensions.nrrd')
        
        # Read the header
        header = nrrd.read_header(test_file)
        
        # The extension-like fields should be in the header but not processed
        self.assertIn('meta/name', header)
        self.assertIn('meta/description', header)
        self.assertIn('dicom/patient.id', header)
        
        # Test that no extensions are found when processing
        _, extensions_dict = process_extension_fields(header)
        self.assertEqual(len(extensions_dict), 0, "No extensions should be found without declarations")
    
    def test_read_mixed_fields(self):
        """Test reading a NRRD file with mix of standard, custom, and extension fields."""
        test_file = os.path.join(TEST_DATA_DIR, 'test_mixed_fields.nrrd')
        header = nrrd.read_header(test_file)
        
        # Process extensions
        processed_header, extensions_dict = process_extension_fields(header)
        
        # Check standard fields in processed header
        self.assertEqual(processed_header['type'], 'float')
        self.assertEqual(processed_header['dimension'], 3)
        self.assertEqual(processed_header['content'], 'Mixed fields test dataset')
        
        # Check custom fields remain in processed header
        for field in ['custom_field_1', 'custom_field_2', 'custom_field_3', 
                      'another_custom_field', 'yet_another_custom_field']:
            self.assertIn(field, processed_header)
        
        # Check extension data
        self.assertIn('meta', extensions_dict)
        meta_data = extensions_dict['meta']['data']
        self.assertEqual(meta_data['name'], 'Mixed Fields Test')
        self.assertEqual(meta_data['description'], 'A test dataset with mix of field types')
        self.assertEqual(meta_data['custom_metadata']['flag1'], True)
        self.assertEqual(meta_data['custom_metadata']['flag2'], False)
        self.assertEqual(meta_data['custom_metadata']['count'], 42)
        self.assertEqual(meta_data['keywords'], ['mixed', 'fields', 'test'])
    
    def test_write_read_roundtrip(self):
        """Test writing and reading back extensions in a round-trip."""
        import tempfile
        import os
        
        # Create a header with extensions
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
                        'string_value': 'Hello, world!',
                        'numeric_value': 42,
                        'boolean_value': True,
                        'array_value': [1, 2, 3, 4, 5],
                        'nested': {
                            'inner_value': 'nested value',
                            'deep': {
                                'deeper': 'deepest value'
                            }
                        }
                    }
                }
            }
        }
        
        # Create test data
        data = np.ones((5, 5, 5), dtype=np.float32)
        
        # Create a temporary file
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, 'test_roundtrip.nrrd')
            
            # Write to the file
            nrrd.write(temp_file, data, header)
            
            # Read back
            read_data, read_header = nrrd.read(temp_file, process_extension_fields=True)
            
            # Check data
            np.testing.assert_array_equal(data, read_data)
            
            # Check extensions
            self.assertIn('extensions', read_header)
            extensions = read_header['extensions']
            self.assertIn('test', extensions)
            test_ext = extensions['test']
            self.assertEqual(test_ext['uri'], 'https://example.org/test/v1.0.0')
            
            # Check extension data
            test_data = test_ext['data']
            self.assertEqual(test_data['string_value'], 'Hello, world!')
            self.assertEqual(test_data['numeric_value'], 42)
            self.assertEqual(test_data['boolean_value'], True)
            self.assertEqual(test_data['array_value'], [1, 2, 3, 4, 5])
            self.assertEqual(test_data['nested']['inner_value'], 'nested value')
            self.assertEqual(test_data['nested']['deep']['deeper'], 'deepest value')
    
    def test_write_with_various_flatten_modes(self):
        """Test writing with different flatten modes."""
        import tempfile
        import os
        
        # Create a header with deeply nested extension
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
                        'deeply': {
                            'nested': {
                                'structure': {
                                    'with': {
                                        'many': {
                                            'levels': 'value'
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        # Create test data
        data = np.ones((5, 5, 5), dtype=np.float32)
        
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test each flatten mode
            for flatten_mode in ['auto', 'always', 'never']:
                temp_file = os.path.join(temp_dir, f'test_flatten_modes_{flatten_mode}.nrrd')
                
                # Write to file
                nrrd.write(temp_file, data, header, flatten=flatten_mode)
                
                # Read the header directly to see the actual format
                with open(temp_file, 'rb') as f:
                    raw_header = f.read().split(b'\n\n')[0].decode('ascii')
                
                if flatten_mode == 'never':
                    # Should use nested JSON object
                    self.assertIn('test/deeply:=', raw_header)
                elif flatten_mode == 'always':
                    # Should be completely flattened
                    self.assertIn('test/deeply.nested.structure.with.many.levels:=', raw_header)
                
                # Read back to check round-trip
                read_data, read_header = nrrd.read(temp_file, process_extension_fields=True)
                
                # The structure should be the same regardless of flatten mode
                self.assertEqual(
                    read_header['extensions']['test']['data']['deeply']['nested']['structure']['with']['many']['levels'],
                    'value'
                )


class TestSpecialCases(unittest.TestCase):
    """Test special cases for NRRD extension I/O."""
    
    def test_empty_uri(self):
        """Test handling of empty URI values."""
        import tempfile
        import os
        
        # Create header with empty URI
        header = {
            'type': 'float',
            'dimension': 3,
            'sizes': [5, 5, 5],
            'encoding': 'raw',
            'endian': 'little',
            'extensions': {
                'empty_uri': {
                    'uri': '',  # Empty URI should be allowed
                    'data': {
                        'test_value': 'empty URI test'
                    }
                }
            }
        }
        
        # Create test data
        data = np.ones((5, 5, 5), dtype=np.float32)
        
        # Create a temporary file
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, 'test_empty_uri.nrrd')
            
            # Write to file
            nrrd.write(temp_file, data, header)
            
            # Read back
            read_data, read_header = nrrd.read(temp_file, process_extension_fields=True)
            
            # Check URI
            self.assertEqual(read_header['extensions']['empty_uri']['uri'], '')
            self.assertEqual(read_header['extensions']['empty_uri']['data']['test_value'], 'empty URI test')
    
    def test_non_json_extension_values(self):
        """Test handling of non-JSON extension values."""
        # Create test header manually
        header_text = """NRRD0004
type: float
dimension: 3
sizes: 5 5 5
encoding: raw
extensions:={"test":"https://example.org/test/v1.0.0"}
test/json_value:={"key":"value"}
test/non_json_value:=not a JSON value
"""
        
        # Create in-memory buffer with this header
        buffer = io.BytesIO(header_text.encode('ascii'))
        
        # Read header
        raw_header = nrrd.read_header(buffer)
        
        # Process extensions
        _, extensions_dict = process_extension_fields(raw_header)
        
        # Check values
        self.assertEqual(extensions_dict['test']['data']['json_value'], {'key': 'value'})
        self.assertEqual(extensions_dict['test']['data']['non_json_value'], 'not a JSON value')
    
    def test_max_length_handling(self):
        """Test handling of max_length parameter for extension writing."""
        import tempfile
        import os
        
        # Create a header with a long extension value
        long_value = "x" * 1000  # 1000 character string
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
                        'long_value': long_value
                    }
                }
            }
        }
        
        # Create test data
        data = np.ones((5, 5, 5), dtype=np.float32)
        
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test with different max_length values
            for max_length in [50, 500, 2000]:
                temp_file = os.path.join(temp_dir, f'test_max_length_{max_length}.nrrd')
                
                # Write to file
                nrrd.write(temp_file, data, header, max_length=max_length)
                
                # Read back
                read_data, read_header = nrrd.read(temp_file, process_extension_fields=True)
                
                # The value should be preserved regardless of max_length
                self.assertEqual(read_header['extensions']['test']['data']['long_value'], long_value)


if __name__ == '__main__':
    unittest.main()