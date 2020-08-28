"""Outputs a human readable html file listing the license scan results."""
from buildstream_license_checker.dependency_element import CheckoutStatus

def write_html_output(results_dict, html_output_path):
    """Outputs a human readable html file listing the license scan results."""
    html_blacklist_results = ""
    html_dependencies = ""

    # get html for dependencies
    for dep in results_dict["licenses detected"]:
        # basic info for each dependency
        dep_start = DEP_HTML_START.format(
            dependency_name=dep["dependency name"],
            dependency_checkout_status=dep["checkout status"],
            full_key_1=dep["full key"][:32],
            full_key_2=dep["full key"][32:],
        )

        # licensecheck results
        dep_middle = ""
        if dep["checkout status"] == CheckoutStatus.checkout_succeeded.value:
            dep_middle += LICENSE_HTML_START.format(
                output_basename=dep["output_filename"]
            )
            for license_line in dep["licensecheck output"]:
                dep_middle += LICENSE_HTML_LINE.format(license_line=license_line)
            dep_middle += LICENSE_HTML_END
        elif dep["checkout status"] == CheckoutStatus.checkout_failed.value:
            dep_middle += CHECKOUT_FAILED_HTML
        elif dep["checkout status"] == CheckoutStatus.fetch_failed.value:
            dep_middle += FETCH_FAILED_HTML

        # pull all the info together (for each dependency)
        html_dependencies += dep_start
        html_dependencies += dep_middle
        html_dependencies += DEP_HTML_END

    # write html to output file
    with open(html_output_path, mode="w") as outfile:
        outfile.write(HTML_START)
        outfile.write(html_blacklist_results)
        outfile.write(html_dependencies)
        outfile.write(HTML_END)


HTML_START = """<!DOCTYPE html>
<html>
<head>
<title>BuildStream license checker - Results Summary</title>
</head>
<style>
.dependency {
  margin: 1em;
  border-width: thin;
  border-style: solid;
}
.dep_fields {
  border-bottom-width: thin;
  border-bottom-style: solid;
  padding: 5px;
}
.licensecheck_output {
  padding: 5px;
}
.license_list {
  column-count: 2
}
.license_item {
  break-inside: avoid
}
</style>
"""

HTML_END = """
</body>
</html>
"""

DEP_HTML_START = """
  <div class="dependency">
    <div class="dep_fields">
      <table>
        <tr><td><strong>Name:</strong></td><td>{dependency_name}</td></tr>
        <tr><td><strong>Checkout:</strong></td><td>{dependency_checkout_status}</td></tr>
        <tr><td><strong>Full&nbsp;Key:</strong></td><td>{full_key_1}<wbr>{full_key_2}</td></tr>
      </table>
    </div>
    <div class="licensecheck_output">
"""

DEP_HTML_END = """
    </div>
  </div>
"""

LICENSE_HTML_START = """
      <strong>Licences: </strong><br>
      <a href="{output_basename}" title="See the detailed license scan output.">(see full output)</a>
      <ul class="license_list">
"""

LICENSE_HTML_LINE = """        <li class="license_item">{license_line}</li>"""

LICENSE_HTML_END = """      </ul>"""

CHECKOUT_FAILED_HTML = """
<strong>NO RESULTS:</strong> No sources checked out.
<p style="max-width: 45em;"><small> The script was unable to check out any sources for this element.
If the element does not have any sources (eg a stack element, or a filter element)
then this is the expected result. Otherwise, this result may mean there has been an
error.</small></p>
"""

FETCH_FAILED_HTML = """
<strong>NO RESULTS:</strong> 'bst fetch' command failed.
<p style="max-width: 45em;"><small> BuildStream's fetch command was unable to fetch
sources for this element. This could mean that there is an error in the element
(such a mistake in the source URL), or it could mean that an external resource is not
currently available for download.</small></p>
"""
