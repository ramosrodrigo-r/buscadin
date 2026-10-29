"""Bounded public-page crawlers. No login, applications, or affiliate URLs."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
import re
import socket
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import httpx
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout

from buscadin_bot.sources.base import RawJob

SOURCES = {
    "micro1": ("micro1", "https://www.micro1.ai/experts/opportunities", {"www.micro1.ai", "jobs.micro1.ai"}),
    "turing": ("Turing", "https://work.turing.com/jobs", {"work.turing.com"}),
    "mercor": ("Mercor", "https://work.mercor.com/explore", {"work.mercor.com"}),
    "alignerr": ("Alignerr", "https://www.alignerr.com/en/jobs", {"www.alignerr.com"}),
}

# Exact asset/API hosts needed to render the public listings. Advertising and
# analytics hosts remain blocked; these hosts cannot become top-level pages.
RESOURCE_HOSTS = {
    "micro1": {"cdn.prod.website-files.com", "d3e54v103j8qbb.cloudfront.net",
               "static-website.sahil-773.workers.dev", "prod-api.micro1.ai"},
    "turing": set(),
    "mercor": {"aws.api.mercor.com", "coil.mercor.com", "d2wgjfzcvyb8t1.cloudfront.net"},
    "alignerr": set(),
}


class CrawlError(ValueError):
    pass


def job_identity(source: str, url: str) -> tuple[str, str] | None:
    """Keep stable company IDs, remove marketing parameters, reject other hosts."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in SOURCES[source][2] or parsed.username or parsed.port not in (None, 443):
        return None
    patterns = {"micro1": r"^/post/([a-f0-9-]{36})/?$", "alignerr": r"^/(?:en/)?jobs/([a-f0-9-]{36})/?$",
                "mercor": r"^/jobs/(list_[A-Za-z0-9_-]+)(?:/[^/]*)?/?$"}
    if source in patterns and (match := re.fullmatch(patterns[source], parsed.path)):
        return match[1], f"https://{parsed.netloc}{parsed.path.rstrip('/')}"
    key = {"turing": "jobId", "mercor": "listingId"}.get(source)
    value = parse_qs(parsed.query).get(key, [""])[0] if key else ""
    if source == "turing" and parsed.path == "/jobs" and re.fullmatch(r"\d+", value):
        return value, f"https://work.turing.com/jobs?jobId={value}"
    if source == "mercor" and parsed.path == "/explore" and re.fullmatch(r"list_[A-Za-z0-9_-]+", value):
        return value, f"https://work.mercor.com/explore?listingId={value}"
    return None


def json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_objects(child)


def scripts(html):
    for script in BeautifulSoup(html, "html.parser").select('script[type="application/ld+json"], script#__NEXT_DATA__'):
        try:
            yield json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue


def parse_detail(source, url, html, *, title="", text="") -> RawJob:
    identity = job_identity(source, url)
    if not identity:
        raise CrawlError("Link da vaga não reconhecido")
    payloads = list(scripts(html))
    schema = next((obj for data in payloads for obj in json_objects(data) if obj.get("@type") == "JobPosting"), None)
    countries, description, salary_min, salary_max, currency, period = [], "", None, None, None, None
    posted, employment, evidence = None, None, {}
    if source == "alignerr":
        job = next((p.get("props", {}).get("pageProps", {}).get("job") for p in payloads if isinstance(p, dict) and p.get("props", {}).get("pageProps", {}).get("job")), None)
        if job:
            if job.get("isActive") is False:
                raise CrawlError("Vaga encerrada na fonte")
            title = job.get("name", "")
            description = job.get("htmlLongDescription") or job.get("longDescription", "")
            code, location = job.get("countryCode"), job.get("location")
            evidence = {"countryCode": code, "location": location, "city": job.get("city")}
            # Observed conflicting countryCode=BR and location=United States.
            # Do not turn this into confirmed Brazilian eligibility.
            if code and (not location or location.lower() in {"remote", "worldwide", "global", code.lower(), "brazil" if code == "BR" else code.lower()}):
                countries = [code]
            elif code:
                description += "\nLocalização conflitante na fonte: " + json.dumps(evidence, ensure_ascii=False)
            salary_min, salary_max = job.get("lowerBoundHourlyRate"), job.get("upperBoundHourlyRate")
            period = "hour" if job.get("salaryType") == "HOURLY" else None
            posted, employment = job.get("firstPostDate"), job.get("jobType")
    if schema:
        title = schema.get("title", "")
        description = schema.get("description", "")
        restrictions = schema.get("applicantLocationRequirements", [])
        if isinstance(restrictions, dict):
            restrictions = [restrictions]
        countries = [v["name"] for v in restrictions if isinstance(v, dict) and v.get("@type") == "Country" and isinstance(v.get("name"), str)]
        evidence = {"applicantLocationRequirements": restrictions}
        salary = schema.get("baseSalary") or {}
        if isinstance(salary, dict) and isinstance(salary.get("value"), dict):
            value = salary["value"]
            salary_min, salary_max = value.get("minValue", value.get("value")), value.get("maxValue", value.get("value"))
            currency, period = salary.get("currency"), value.get("unitText")
        posted, employment = schema.get("datePosted"), schema.get("employmentType")
        until = schema.get("validThrough")
        if until:
            try:
                if datetime.fromisoformat(until.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    raise CrawlError("Vaga expirada na fonte")
            except ValueError as error:
                if isinstance(error, CrawlError):
                    raise
    if source == "turing" and not description:
        description = text
    if not title.strip() or len(BeautifulSoup(description, "html.parser").get_text(strip=True)) < 80:
        raise CrawlError("Descrição completa não encontrada; página pode ter mudado")
    try:
        date = datetime.fromisoformat(posted.replace("Z", "+00:00")) if posted else None
    except (ValueError, AttributeError):
        date = None
    # HTML is normalized by the collector, escaped by the admin renderer.
    return RawJob(source=source, source_job_id=identity[0], company=SOURCES[source][0],
        title=title.strip(), description=description, source_url=identity[1], application_url=identity[1],
        location_restrictions=countries, min_salary=salary_min, max_salary=salary_max,
        currency=currency, salary_period=period, posted_at=date,
        employment_type=employment if isinstance(employment, str) else None,
        raw={"location_evidence": evidence})


@dataclass
class CrawlReport:
    source: str
    discovered: int = 0
    skipped: int = 0
    pages: int = 0
    failed: int = 0
    limited: bool = False
    errors: list[str] = field(default_factory=list)


class CompanyCrawler:
    def __init__(self, name, known_ids=(), *, max_new=30, max_pages=5):
        if name not in SOURCES:
            raise ValueError("Fonte desconhecida")
        self.name, self.known = name, set(known_ids)
        self.max_new, self.max_pages = max_new, max_pages
        self.report = CrawlReport(name)
        self.seen = set()
        self.robots = {}
        self.http = None

    async def allowed(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in SOURCES[self.name][2]:
            return False
        base = f"https://{parsed.hostname}"
        if base not in self.robots:
            response = await self.http.get(base + "/robots.txt")
            if response.status_code == 404:
                content = "User-agent: *\nAllow: /"
            elif response.status_code == 200 and not response.text.lstrip().startswith("<"):
                content = response.text
            else:
                raise CrawlError("Não foi possível verificar robots.txt; coleta interrompida")
            parser = RobotFileParser()
            parser.parse(content.splitlines())
            self.robots[base] = parser
        return self.robots[base].can_fetch("BuscadinBot", url)

    async def navigate(self, page, url):
        if not await self.allowed(url):
            raise CrawlError("Página não permitida por robots.txt ou domínio")
        await asyncio.sleep(1)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if response and response.status >= 400:
            raise CrawlError(f"Fonte retornou HTTP {response.status}")

    async def guard(self, route):
        request = route.request
        parsed = urlsplit(request.url)
        host = parsed.hostname or ""
        try:
            private = not ipaddress.ip_address(host).is_global
        except ValueError:
            private = host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
        if (private or parsed.scheme != "https" or host not in (SOURCES[self.name][2] | RESOURCE_HOSTS[self.name])
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)
                or request.resource_type in {"image", "media", "font"}):
            return await route.abort()
        if request.is_navigation_request() and request.frame.parent_frame is None:
            if not await self.allowed(request.url):
                return await route.abort()
        await route.continue_()

    async def fetch_jobs(self):
        jobs = []
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "BuscadinBot/1.0"}) as self.http:
            async with async_playwright() as playwright:
                # Pin every permitted hostname for this browser lifetime: checking
                # DNS and then letting Chromium resolve again permits rebinding.
                rules = []
                for host in sorted(SOURCES[self.name][2] | RESOURCE_HOSTS[self.name]):
                    addresses = await asyncio.get_running_loop().getaddrinfo(
                        host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
                    ips = {item[4][0] for item in addresses}
                    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                        raise CrawlError("DNS da fonte aponta para endereço não público")
                    rules.append(f"MAP {host} {sorted(ips)[0]}")
                rules.append("MAP * ~NOTFOUND")
                browser = await playwright.chromium.launch(args=[
                    "--host-resolver-rules=" + ",".join(rules), "--no-proxy-server",
                    "--disable-quic",
                ])
                try:
                    context = await browser.new_context(service_workers="block")
                    await context.route("**/*", self.guard)
                    listing, detail = await context.new_page(), await context.new_page()
                    listing.set_default_timeout(12000)
                    detail.set_default_timeout(12000)
                    await self.navigate(listing, SOURCES[self.name][1])
                    selector = {"micro1": 'a[href*="jobs.micro1.ai/post/"]', "alignerr": 'a[href*="/jobs/"]',
                                "mercor": '[data-test="listing-title"]', "turing": 'h3.line-clamp-2'}[self.name]
                    await listing.locator(selector).first.wait_for(state="attached", timeout=25000)
                    for page_number in range(self.max_pages):
                        self.report.pages = page_number + 1
                        if self.name == "turing":
                            await self.turing_page(listing, jobs)
                        else:
                            urls = await self.links(listing)
                            for url in urls:
                                if len(jobs) >= self.max_new:
                                    break
                                if not self.accept(url):
                                    continue
                                try:
                                    await self.navigate(detail, url)
                                    if self.name == "micro1":
                                        await detail.wait_for_function("() => [...document.querySelectorAll('script[type=\"application/ld+json\"]')].some(x => x.textContent.includes('JobPosting'))", timeout=20000)
                                    elif self.name == "mercor":
                                        await detail.locator('h1').first.wait_for()
                                    jobs.append(parse_detail(self.name, url, await detail.content()))
                                except (CrawlError, BrowserTimeout) as error:
                                    self.failure(error)
                        if len(jobs) >= self.max_new:
                            self.report.limited = True
                            break
                        if page_number + 1 == self.max_pages:
                            self.report.limited = True
                            break
                        if not await self.next_page(listing):
                            break
                finally:
                    await browser.close()
        if not self.report.discovered:
            raise CrawlError("Nenhum anúncio reconhecido; verifique se a página mudou")
        return jobs

    def failure(self, error):
        self.report.failed += 1
        message = str(error) if isinstance(error, CrawlError) else "Tempo limite ao carregar anúncio"
        if message not in self.report.errors:
            self.report.errors.append(message[:200])

    def accept(self, url):
        identity = job_identity(self.name, url)
        if not identity or identity[0] in self.seen:
            return False
        self.seen.add(identity[0])
        self.report.discovered += 1
        if identity[0] in self.known:
            self.report.skipped += 1
            return False
        return True

    async def links(self, page):
        if self.name == "mercor":
            # Public SEO list gives canonical description URLs, not /apply routes.
            objects = [obj for data in scripts(await page.content()) for obj in json_objects(data)]
            urls = [obj["url"] for obj in objects if obj.get("@type") == "ListItem" and isinstance(obj.get("url"), str) and job_identity("mercor", obj["url"])]
            if urls:
                return list(dict.fromkeys(urls))
            raise CrawlError("Listagem pública da Mercor ainda não carregou os links")
        return await page.locator('a[href]').evaluate_all("xs => xs.map(x => x.href)")

    async def turing_page(self, page, jobs):
        titles = await page.locator('h3.line-clamp-2').all_text_contents()
        for title in titles:
            if len(jobs) >= self.max_new:
                break
            try:
                await page.get_by_role("heading", name=title, exact=True).first.click()
                await page.wait_for_url(re.compile(r"jobId=\d+"), wait_until="domcontentloaded")
                url = page.url
                if self.accept(url):
                    await page.get_by_text("Job Description", exact=True).first.wait_for()
                    text = await page.locator('h2').filter(has_text=title).first.evaluate("el => {let n=el; while(n.parentElement && !n.innerText.includes('Job Description')) n=n.parentElement; return n.innerText;}")
                    jobs.append(parse_detail("turing", url, "", title=title, text=text))
            except (CrawlError, BrowserTimeout) as error:
                self.failure(error)
            finally:
                for button in await page.get_by_role("button", name="Close", exact=True).all():
                    if await button.is_visible():
                        await button.click()
                        break
                await asyncio.sleep(1)

    async def next_page(self, page):
        selector = {"micro1": 'a[href*="jobs.micro1.ai/post/"]', "alignerr": 'a[href*="/jobs/"]',
                    "mercor": '[data-test="listing-title"]', "turing": 'h3.line-clamp-2'}[self.name]
        before = await page.locator(selector).evaluate_all("xs => xs.map(x => x.id + x.textContent).join('|')")
        if self.name in {"alignerr", "turing"}:
            button = page.get_by_role("button", name="Load more roles", exact=True)
        elif self.name == "mercor":
            button = page.locator('[aria-label="Go to next page"]')
        else:
            # micro1 uses infinite scroll, rather than a numbered page URL.
            sentinel = page.locator('.scroll-sentinel')
            if not await sentinel.count():
                return False
            await sentinel.scroll_into_view_if_needed()
            try:
                await page.wait_for_function("([selector, old]) => [...document.querySelectorAll(selector)].map(x => x.id + x.textContent).join('|') !== old", arg=[selector, before], timeout=15000)
                return True
            except BrowserTimeout:
                self.report.limited = True
                self.failure(CrawlError("Não foi possível carregar a próxima página"))
                return False
        if not await button.count() or not await button.first.is_enabled() or await button.first.get_attribute("aria-disabled") == "true":
            return False
        await button.first.click()
        try:
            await page.wait_for_function("([selector, old]) => [...document.querySelectorAll(selector)].map(x => x.id + x.textContent).join('|') !== old", arg=[selector, before], timeout=15000)
        except BrowserTimeout:
            self.report.limited = True
            self.failure(CrawlError("Não foi possível carregar a próxima página"))
            return False
        await asyncio.sleep(1)
        return True
