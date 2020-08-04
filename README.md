# BuildStream License Checker

This project is intended to produce a license-checking utility for BuildStream 
projects.

The utility will check out the sources of a given element into a temporary
folder, run a license-scanning tool called licensecheck, and then process the
results.

The utility will be written as a python script, using subprocess to call
buildstream functions and licensecheck.

### Usage

```
buildstream-license-checker [--deps <dep-type>] [--track] [--] <elements>
buildstream-license-checker [-h|--help]

	--deps [none|run|all]
		determines which dependencies to scan
	        options will have the same meaning as they do for bst show

		none:  No dependencies, just the element itself
		run:   Runtime dependencies, including the element itself
		all:   All dependencies

	--track 
		run the bst track command on each dependency before checking
		out sources.

	--	
		End options. Anything after this will be treated as an element
		name.

	<elements>
		One or more element names.
```

The script works by identifying the list of approprite dependencies for each
element, and then for every element performing `bst source checkout` to produce
a temporary folder containing the element's sources. That folder is then scanned
for license information using another utility.

`bst source checkout` will fail if the source needs to be tracked. Either
run the buildstream `track` command on the element manually, or use the
`--track` option. Note that `--track` will track every element and dependency,
and may update existing refs.

### License-scanning

TBD
One option under consideration is [Fossology](https://www.fossology.org/).

### Output Format

TBD
