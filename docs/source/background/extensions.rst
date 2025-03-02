Extensions
==========

Overview
-----------

The NRRD Extensions specification adds a mechanism for storing structured metadata in NRRD files using JSON.
This allows users to include complex hierarchical data alongside their volume data while maintaining
backward compatibility with existing NRRD parsers.

Key features of the NRRD Extensions mechanism:

1. **Structured Metadata**: Store complex, hierarchical data in a structured format
2. **JSON-based**: Uses JSON as the serialization format for compatibility and flexibility
3. **Backward Compatible**: Files with extensions are still readable by standard NRRD parsers
4. **Namespace Support**: Extensions are organized into namespaces to avoid conflicts

Extension Format
-----------------

Extensions consist of two main components:

1. **Extension Declarations**: Define the extensions used in the file and their URIs
2. **Extension Fields**: The actual data fields containing the metadata

Extension Declarations
~~~~~~~~~~~~~~~~~~~~~~

Extension declarations define the namespaces used in the file and link them to URI specifications.
They appear in the NRRD header with the prefix "extensions.", for example::

    extensions.meta:="https://example.org/nrrd/metadata/v1"
    extensions.dicom:="https://example.org/nrrd/dicom/v1"

Extension Fields
~~~~~~~~~~~~~~~

Extension fields contain the actual metadata and are identified by a prefix matching
one of the declared extensions, followed by a separator (typically "/") and the field name::

    meta/author:="Jane Doe"
    meta/created:="2023-01-15T14:30:00Z"
    dicom/patientID:="12345"
    dicom/studyDate:="20230101"

Complex Hierarchical Data
-------------------------

Extensions support complex hierarchical data structures which are automatically
flattened when writing and reconstructed when reading. This follows JSON Path notation:

* Nested objects use dot notation: `meta/settings.threshold:=0.75`
* Arrays use index notation: `meta/categories[0]:="tissue"`
* Combined: `meta/regions[0].name:="tumor"`

Example
-------

A hierarchical data structure like::

    {
      "analysis": {
        "segmentation": {
          "method": "automatic",
          "params": {
            "threshold": 0.75,
            "iterations": 3
          },
          "regions": [
            {
              "id": 1,
              "name": "tumor",
              "volume": 1250.5
            },
            {
              "id": 2,
              "name": "edema",
              "volume": 3621.2
            }
          ]
        }
      }
    }

Would be flattened and written to the NRRD file as::

    analysis/segmentation.method:="automatic"
    analysis/segmentation.params.threshold:=0.75
    analysis/segmentation.params.iterations:=3
    analysis/segmentation.regions[0].id:=1
    analysis/segmentation.regions[0].name:="tumor"
    analysis/segmentation.regions[0].volume:=1250.5
    analysis/segmentation.regions[1].id:=2
    analysis/segmentation.regions[1].name:="edema"
    analysis/segmentation.regions[1].volume:=3621.2

Using Extensions in PyNRRD
--------------------------

In PyNRRD, extensions are handled through two special fields in the header dictionary:

1. **extensions**: A dictionary mapping extension names to URIs
2. **extension_data**: A dictionary containing the hierarchical data organized by extension

For example::

    header = {
        'extensions': {
            'meta': 'https://example.org/meta',
            'dicom': 'https://example.org/dicom'
        },
        'extension_data': {
            'meta': {
                'author': 'Jane Doe',
                'date': '2023-01-01',
                'version': 1.0
            },
            'dicom': {
                'patientID': '12345',
                'studyDate': '20230101'
            }
        }
    }

When writing a NRRD file, PyNRRD automatically flattens and serializes the extension data:

.. code-block:: python

    nrrd.write('with_extensions.nrrd', data, header)

When reading a NRRD file with extensions, PyNRRD reconstructs the hierarchical structure:

.. code-block:: python

    data, header = nrrd.read('with_extensions.nrrd')
    
    # Access extension data
    meta_author = header['extension_data']['meta']['author']
    dicom_id = header['extension_data']['dicom']['patientID']