# BuildStream License Checker

This project is intended to produce a license-checking utility for BuildStream 
projects.

The utility will check out the sources of a given element into a temporary
folder, run a license-scanning tool, and then process the results.

The utility will be written as a python script, using subprocess to call
buildstream functions and licensecheck.

### Install

Buildstream License Checker is a python package, and can be installed with pip. Navigate
to the top level `buildstream_license_checker` directory, and run the command
```
pip3 install .
```

### Usage

```
usage: bst_license_checker.py [-h] [-t] [-d DEPS_TYPE] [-i IGNORELIST_FILENAME]
                              -w WORKING_DIRECTORY -o OUTPUT_DIRECTORY
                              ELEMENT_NAMES [ELEMENT_NAMES ...]

positional arguments:
  ELEMENT_NAMES         One or more elements to be checked.

optional arguments:
  -h, --help            show this help message and exit
  -d DEPS_TYPE, --deps DEPS_TYPE
                        The type of dependencies to scan. Will be passed
                        directly to the 'bst show' command. Choose from: none,
                        run, all. Defaults to: run.
  -t, --track           Run the bst track command on each dependency before
                        checking licenses.
  -o OUTPUT_DIRECTORY, --output OUTPUT_DIRECTORY
                        The path to an output directory, in which to store
                        license results. Will be created if it doesn't already
                        exist. Directory must be empty.
  -w WORKING_DIRECTORY, --work WORKING_DIRECTORY
                        License results will be created here first, and saved.
                        Can be reused (does not need to be emptied between
                        invocations). Can be used as a cache: previously
                        processed results will be reused if the hash-key has
                        not changed.
  -i IGNORELIST_FILENAME, --ignorelist IGNORELIST_FILENAME
                        Filename for a list of elements names to ignore.
                        Ignored elements will not be fetched, tracked or
                        scanned for licenses. Element names in the ignore list
                        file should be separated by line breaks (one element
                        name per line). Lines which start with a hash (#) are
                        treated as comments.
```

### How it works

When run, the script executes the following stages:

1) The script runs `bst show` to collect a list of all relevant dependencies.
The elements named in `ELEMENT_NAMES` are passed verbatim to bst show, along
with the `--deps` option. Any elements named in the `ignorelist` file are
removed from the list at this stage.

The resulting list is the full list of elements that will be scanned for
licenses. Internally, the script refers to these as "dependency elements" to
distinguish them from the intial list of elements supplied by the user as
`ELEMENT NAMES`.

2) If the `-t` option is used, the script runs the `bst track` command on all of
the dependency elements. This may change the full-key for some dependency
elements.

3) The script runs `bst fetch` on all of the dependency elements to ensure that
BuildStream has an up to date cache of all sources. This may change the status
of some dependency elements. `bst show` is run again, to get up to date values
for full-key and element statuses.

4) The script then iterates through each of the dependency elements. For each
element, the script checks out the source code of that element into a temporary
folder, and uses license scanning software to detect the licences that apply.
For each dependency element, an output file is saved to the working directory
and then copied to the output directory.

4a) Note: if the script has already scanned an element on a previous occasion,
then the output file may already exist in the working directory. If the element
name and the element full key haven't changed, then the script will not check
out or scan the element. Instead, it will simply re-use the existing result
file. In this way, the working directory can serve as a cache.

5) The script summarises the output files and produces a list of detected
licenses for each element. The results are returned in a dictionary object. The
dictionry object is used to generate a machine-readable json summary file, and a
human readable html summary file. The json format is a direct json dump of the
results, and has the following format:

```
{
  "dependency-list": [
    {
      "dependency-name": "bootstrap/acl.bst",
      "full-key": "cd819edf4915f403f9864aa6f69f5395b033ed2aed671507452e1e35783f8905",
      "checkout-status": "checkout succeeded",
      "detected-licenses": [
        "GNU General Public License v2.0 or later",
        "GNU Lesser General Public License v2.1 or later",
        "GNU Lesser General Public License, Version 2.1 GNU General Public License, Version 2"
      ],
      "output-filename": "bootstrap-acl.bst--cd819edf4915f403f9864aa6f69f5395b033ed2aed671507452e1e35783f8905.licensecheck_output.txt"
    },
    ...
    ...
    {
      "dependency-name": "bootstrap/attr.bst",
      "full-key": "bee8d33a7c1cd7b5b0ccbbd934bd1dfc551da5d3b6f44b1da37c06817f554790",
      "checkout-status": "checkout succeeded",
      "detected-licenses": [
        "GNU General Public License v2.0 or later",
        "GNU Lesser General Public License v2.1 or later",
        "GNU Lesser General Public License, Version 2.1 GNU General Public License, Version 2"
      ],
      "output-filename": "bootstrap-attr.bst--bee8d33a7c1cd7b5b0ccbbd934bd1dfc551da5d3b6f44b1da37c06817f554790.licensecheck_output.txt"
    },
    ...
    ...
  ]
}
```

### License scanning software

The license scanning software currently used, is "licensecheck", as found on
cpan: https://metacpan.org/pod/distribution/App-Licensecheck/bin/licensecheck

### Notes

`bst source checkout` will fail if the source needs to be tracked. To proceed,
either run the buildstream `track` command on the element manually, or use the
`--track` option. (Note that `--track` will track every element and dependency,
and can update existing refs.)
