.. _extensions:

=======================================================
Extensions
=======================================================

.. currentmodule:: nrrd.extensions

The extensions module provides support for storing structured metadata in NRRD files
using a JSON-based format while maintaining backward compatibility.

Functions
=======================================================

.. autofunction:: process_extension_fields
.. autofunction:: prepare_extensions_for_writing

Extension Data Structure
=======================================================

When using the NRRD extensions mechanism, users should provide a special field
in the header:

**extensions**: A dictionary mapping extension names to objects with 'uri' and 'data' fields:

- **uri**: A string containing the URI that identifies the extension specification
- **data**: A dictionary containing the hierarchical data for the extension

Example::

    'extensions': {
        'meta': {
            'uri': 'https://example.org/meta',
            'data': {
                'author': 'Jane Doe',
                'date': '2023-01-01',
                'version': 1.0
            }
        },
        'dicom': {
            'uri': 'https://example.org/dicom',
            'data': {
                'patientID': '12345',
                'studyDate': '20230101'
            }
        }
    }

Requirements and Backward Compatibility
---------------------------------------

The NRRD extensions specification requires that any file containing extension fields must declare
the extensions they use. If PyNRRD encounters keys that look like extension fields (contain the 
namespace separator) but no extensions are declared, it will issue a warning and pass through 
these fields unchanged for backward compatibility.

Extension Field Serialization
=======================================================

When writing NRRD files, extension data is automatically flattened and serialized
to JSON format. When reading NRRD files with extensions, the flattened extension
fields are reconstructed into a hierarchical structure.

For example, an extension with hierarchical data like this::

    'extensions': {
        'analysis': {
            'uri': 'https://example.org/analysis',
            'data': {
                'segmentation': {
                    'method': 'automatic',
                    'regions': [
                        {'id': 1, 'name': 'tumor'},
                        {'id': 2, 'name': 'edema'}
                    ]
                }
            }
        }
    }

Will be flattened and written to the NRRD file as::

    analysis/segmentation.method:="automatic"
    analysis/segmentation.regions[0].id:=1
    analysis/segmentation.regions[0].name:="tumor"
    analysis/segmentation.regions[1].id:=2
    analysis/segmentation.regions[1].name:="edema"

Low-Level Functions
=======================================================

The following functions implement the core extensions functionality and
are typically used internally by the higher-level functions:

.. autofunction:: parse_extensions_from_header
.. autofunction:: find_extension_keys
.. autofunction:: parse_json_value
.. autofunction:: serialize_nrrd_json
.. autofunction:: get_field_type_extension