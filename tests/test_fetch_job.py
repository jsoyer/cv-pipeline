"""Tests for fetch-job.py — URL parsing, text extraction, company detection."""

import importlib

import pytest

# Import the module from scripts/
fetch_job = importlib.import_module("fetch-job")


# ---------------------------------------------------------------------------
# _extract_from_url
# ---------------------------------------------------------------------------

class TestExtractFromUrl:
    def test_greenhouse(self):
        company, _ = fetch_job._extract_from_url(
            "https://job-boards.greenhouse.io/anthropic/jobs/12345"
        )
        assert company.lower() == "anthropic"

    def test_lever(self):
        company, _ = fetch_job._extract_from_url(
            "https://jobs.lever.co/figma/abc-123"
        )
        assert company.lower() == "figma"

    def test_workday(self):
        company, _ = fetch_job._extract_from_url(
            "https://sailpoint.wd1.myworkdayjobs.com/en-US/careers/job/12345"
        )
        assert company.lower() == "sailpoint"

    def test_ashby(self):
        company, _ = fetch_job._extract_from_url(
            "https://cloudflare.ashbyhq.com/jobs/12345"
        )
        assert company.lower() == "cloudflare"

    def test_smartrecruiters(self):
        company, _ = fetch_job._extract_from_url(
            "https://jobs.smartrecruiters.com/Datadog/12345-senior-se"
        )
        assert company.lower() == "datadog"

    def test_unknown_url(self):
        company, position = fetch_job._extract_from_url(
            "https://example.com/careers/apply"
        )
        assert company == ""
        assert position == ""

    def test_hyphenated_company(self):
        company, _ = fetch_job._extract_from_url(
            "https://job-boards.greenhouse.io/palo-alto-networks/jobs/123"
        )
        assert "palo" in company.lower()
        assert "alto" in company.lower()


# ---------------------------------------------------------------------------
# _extract_from_html
# ---------------------------------------------------------------------------

class TestExtractFromHtml:
    def test_og_site_name(self):
        html = '<meta property="og:site_name" content="Anthropic">'
        company, _ = fetch_job._extract_from_html(html)
        assert company == "Anthropic"

    def test_og_title_at_pattern(self):
        html = '<meta property="og:title" content="Senior SE at Figma">'
        company, position = fetch_job._extract_from_html(html)
        assert "figma" in company.lower()
        assert "senior" in position.lower()

    def test_title_dash_pattern(self):
        html = "<title>Datadog - Staff Engineer</title>"
        company, position = fetch_job._extract_from_html(html)
        assert "datadog" in company.lower()
        assert "staff" in position.lower()

    def test_h1_fallback(self):
        html = "<html><body><h1>VP of Engineering</h1></body></html>"
        _, position = fetch_job._extract_from_html(html)
        assert "vp" in position.lower()

    def test_empty_html(self):
        company, position = fetch_job._extract_from_html("")
        assert company == ""
        assert position == ""


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_strips_script_tags(self):
        html = "<html><body><script>alert(1)</script><p>Job description</p></body></html>"
        text = fetch_job.extract_text(html)
        assert "Job description" in text
        assert "alert" not in text

    def test_strips_nav_footer(self):
        html = "<html><body><nav>Menu</nav><main>Content here</main><footer>Copyright</footer></body></html>"
        text = fetch_job.extract_text(html)
        assert "Content here" in text
        assert "Menu" not in text
        assert "Copyright" not in text

    def test_finds_job_container(self):
        html = '<html><body><div>Noise</div><article>The real job posting</article></body></html>'
        text = fetch_job.extract_text(html)
        assert "real job posting" in text

    def test_collapses_whitespace(self):
        html = "<html><body><p>Line 1</p>\n\n\n\n<p>Line 2</p></body></html>"
        text = fetch_job.extract_text(html)
        assert "\n\n\n" not in text


# ---------------------------------------------------------------------------
# extract_job_info
# ---------------------------------------------------------------------------

class TestExtractJobInfo:
    def test_combines_url_and_html(self):
        url = "https://job-boards.greenhouse.io/anthropic/jobs/123"
        html = '<meta property="og:title" content="Solutions Architect at Anthropic">'
        info = fetch_job.extract_job_info(url, "", html)
        assert info["company"].lower() == "anthropic"
        assert "solutions" in info["position"].lower() or "architect" in info["position"].lower()

    def test_url_company_html_position(self):
        url = "https://jobs.lever.co/stripe/abc-123"
        html = "<html><body><h1>Staff Software Engineer</h1></body></html>"
        info = fetch_job.extract_job_info(url, "", html)
        assert "stripe" in info["company"].lower()
        assert "staff" in info["position"].lower()
