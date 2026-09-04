import time
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from curl_cffi import requests
import pandas as pd
from colorama import Fore, Style, init

init(autoreset=True)

WEBSITE = "https://www.olx.pt"

# Number of individual ad pages to fetch simultaneously.
# 5 is a reasonable balance between speed and load.
MAX_DETAIL_WORKERS = 5

AUTO_KEYWORDS = [
    "automático",
    "automatica",
    "automática",
    "automatic",
    "auto."
]

MANUAL_KEYWORDS = [
    "manual",
    "man.",
    "mt"
]


# ============================================================
# FETCH SEARCH PAGE
# ============================================================

def fetch_page(session, query, page):
    """Fetches an OLX search page."""

    url = f"{WEBSITE}/ads/q-{query}/?page={page}"

    try:
        response = session.get(
            url,
            impersonate="chrome124",
            timeout=15
        )

        response.raise_for_status()

        return BeautifulSoup(
            response.text,
            "lxml"
        )

    except Exception as e:

        print(
            Fore.RED +
            f"Error fetching page {page}: {e}" +
            Style.RESET_ALL
        )

        return None


# ============================================================
# FETCH INDIVIDUAL AD
# ============================================================

def fetch_ad_page(url):
    """
    Fetches an individual OLX advertisement.

    A new session is created for each worker thread.
    """

    try:

        with requests.Session() as session:

            response = session.get(
                url,
                impersonate="chrome124",
                timeout=15
            )

            response.raise_for_status()

            return BeautifulSoup(
                response.text,
                "lxml"
            )

    except Exception:
        return None


# ============================================================
# TOTAL PAGES
# ============================================================

def get_total_pages(soup):

    if soup is None:
        return 1

    # --------------------------------------------------------
    # Total result count
    # --------------------------------------------------------

    count_span = soup.find(
        attrs={
            "data-testid": "total-count"
        }
    )

    if count_span:

        try:

            total_text = count_span.get_text(
                strip=True
            )

            digits = re.findall(
                r"\d+",
                total_text
                .replace(".", "")
                .replace(" ", "")
                .replace("\xa0", "")
            )

            if digits:

                total_ads = int(
                    digits[0]
                )

                return max(
                    1,
                    (total_ads + 39) // 40
                )

        except Exception:
            pass

    # --------------------------------------------------------
    # Pagination fallback
    # --------------------------------------------------------

    pagination_container = (
        soup.find(
            attrs={
                "data-testid": "pagination-list"
            }
        )
        or
        soup.find(
            "ul",
            class_=re.compile(r"\bcss-")
        )
    )

    if pagination_container:

        links = pagination_container.find_all(
            "a"
        )

        numeric_pages = []

        for a in links:

            txt = a.get_text(
                strip=True
            )

            if txt.isdigit():
                numeric_pages.append(
                    int(txt)
                )

        if numeric_pages:
            return max(
                numeric_pages
            )

    return 1


# ============================================================
# NUMERIC PARSER
# ============================================================

def parse_numeric(text):

    if not text:
        return None

    cleaned = (
        text
        .replace("€", "")
        .replace("\xa0", " ")
        .strip()
    )

    cleaned = cleaned.replace(
        ".",
        ""
    )

    cleaned = cleaned.replace(
        ",",
        "."
    )

    match = re.search(
        r"\d+(?:\.\d+)?",
        cleaned
    )

    if match:

        try:
            return float(
                match.group()
            )

        except ValueError:
            return None

    return None


# ============================================================
# YEAR PARSER
# ============================================================

def parse_year(text):

    if not text:
        return None

    text = (
        text
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .strip()
    )

    # Explicit OLX parameter
    match = re.search(
        r"\bAno\s*:\s*(\d{4})\b",
        text,
        re.IGNORECASE
    )

    if match:

        year = int(
            match.group(1)
        )

        if 1900 <= year <= 2100:
            return year

    # Search result fallback
    match = re.search(
        r"\b(19\d{2}|20\d{2})\b",
        text
    )

    if match:

        year = int(
            match.group(1)
        )

        if 1900 <= year <= 2100:
            return year

    return None


# ============================================================
# MILEAGE PARSER
# ============================================================

def parse_mileage(text):

    if not text:
        return None

    text = (
        text
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .strip()
    )

    # --------------------------------------------------------
    # OLX parameter
    #
    # Quilómetros: 10.000 km
    # --------------------------------------------------------

    match = re.search(
        r"Quilómetros\s*:\s*([\d.\s]+)\s*km",
        text,
        re.IGNORECASE
    )

    if match:

        mileage_string = re.sub(
            r"[^\d]",
            "",
            match.group(1)
        )

        if mileage_string:

            try:
                return int(
                    mileage_string
                )

            except ValueError:
                pass

    # --------------------------------------------------------
    # Search result:
    #
    # 2021 - 9.420 km
    # --------------------------------------------------------

    match = re.search(
        r"([\d.\s]+)\s*km\b",
        text,
        re.IGNORECASE
    )

    if match:

        mileage_string = re.sub(
            r"[^\d]",
            "",
            match.group(1)
        )

        if mileage_string:

            try:
                return int(
                    mileage_string
                )

            except ValueError:
                pass

    # --------------------------------------------------------
    # Title:
    #
    # 9420 kms
    # --------------------------------------------------------

    match = re.search(
        r"([\d.\s]+)\s*kms\b",
        text,
        re.IGNORECASE
    )

    if match:

        mileage_string = re.sub(
            r"[^\d]",
            "",
            match.group(1)
        )

        if mileage_string:

            try:
                return int(
                    mileage_string
                )

            except ValueError:
                pass

    return None


# ============================================================
# GEARBOX PARSER
# ============================================================

def parse_gearbox(text):

    if not text:
        return None

    text_lower = (
        text
        .replace("\xa0", " ")
        .strip()
        .lower()
    )

    # Automatic first
    if (
        "automático" in text_lower
        or
        "automática" in text_lower
        or
        "automatica" in text_lower
        or
        "automatic" in text_lower
        or
        "auto." in text_lower
    ):
        return "Automático"

    if "manual" in text_lower:
        return "Manual"

    return None


# ============================================================
# PARSE INDIVIDUAL AD
# ============================================================

def parse_ad_details(soup):

    year = None
    mileage = None
    caixa = "N/A"

    if soup is None:
        return year, mileage, caixa

    # --------------------------------------------------------
    # Find parameters container
    # --------------------------------------------------------

    params_div = soup.find(
        attrs={
            "data-testid":
                "ad-parameters-container"
        }
    )

    if params_div:

        parameter_items = params_div.find_all(
            "p",
            recursive=False
        )

        if not parameter_items:

            parameter_items = (
                params_div.find_all("p")
            )

        for p in parameter_items:

            item = p.get_text(
                " ",
                strip=True
            )

            if not item:
                continue

            # Year
            if year is None:

                parsed_year = parse_year(
                    item
                )

                if parsed_year is not None:
                    year = parsed_year

            # Mileage
            if mileage is None:

                parsed_mileage = parse_mileage(
                    item
                )

                if parsed_mileage is not None:
                    mileage = parsed_mileage

            # Gearbox
            if caixa == "N/A":

                parsed_gearbox = parse_gearbox(
                    item
                )

                if parsed_gearbox:
                    caixa = parsed_gearbox

    # --------------------------------------------------------
    # Entire page fallback
    # --------------------------------------------------------

    page_text = soup.get_text(
        " ",
        strip=True
    )

    # Year
    if year is None:

        match = re.search(
            r"Ano\s*:\s*(\d{4})",
            page_text,
            re.IGNORECASE
        )

        if match:

            candidate = int(
                match.group(1)
            )

            if 1900 <= candidate <= 2100:
                year = candidate

    # Mileage
    if mileage is None:

        mileage = parse_mileage(
            page_text
        )

    # Gearbox
    if caixa == "N/A":

        gearbox_match = re.search(
            r"Tipo de Caixa\s*:\s*(.{0,100})",
            page_text,
            re.IGNORECASE
        )

        if gearbox_match:

            parsed_gearbox = parse_gearbox(
                gearbox_match.group(0)
            )

            if parsed_gearbox:
                caixa = parsed_gearbox

    return year, mileage, caixa


# ============================================================
# FIND CARDS
# ============================================================

def find_cards(soup):

    if soup is None:
        return []

    # Primary method
    cards = soup.find_all(
        attrs={
            "data-cy": "l-card"
        }
    )

    if cards:
        return cards

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    cards = []

    prices = soup.find_all(
        attrs={
            "data-testid": "ad-price"
        }
    )

    for price_element in prices:

        current = price_element

        for _ in range(8):

            if current.parent is None:
                break

            current = current.parent

            if current.find(
                "a",
                href=re.compile(
                    r"/(?:d/)?anuncio/"
                )
            ):

                cards.append(
                    current
                )

                break

    return cards


# ============================================================
# PARSE SEARCH PAGE
# ============================================================

def parse_search_card(card):

    # --------------------------------------------------------
    # Link
    # --------------------------------------------------------

    link_tag = card.find(
        "a",
        href=re.compile(
            r"/(?:d/)?anuncio/"
        )
    )

    if not link_tag:
        return None

    link = link_tag.get(
        "href",
        ""
    )

    if not link:
        return None

    if link.startswith("/"):
        link = WEBSITE + link

    # Remove query parameters
    clean_link = link.split("?")[0]

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    title_tag = (
        card.find("h4")
        or
        card.find("h6")
        or
        link_tag.find(
            ["h4", "h6"]
        )
    )

    title = (
        title_tag.get_text(
            strip=True
        )
        if title_tag
        else "No Title"
    )

    title_lower = title.lower()

    # --------------------------------------------------------
    # Price
    # --------------------------------------------------------

    price_tag = card.find(
        attrs={
            "data-testid": "ad-price"
        }
    )

    if not price_tag:
        price_tag = card.find("p")

    raw_price = (
        price_tag.get_text(
            strip=True
        )
        if price_tag
        else ""
    )

    price = parse_numeric(
        raw_price
    )

    # --------------------------------------------------------
    # Search card text
    # --------------------------------------------------------

    card_text = card.get_text(
        " ",
        strip=True
    )

    # Try to get details directly from card
    year = parse_year(
        card_text
    )

    mileage = parse_mileage(
        card_text
    )

    caixa = (
        parse_gearbox(card_text)
        or
        "N/A"
    )

    return {
        "title": title,
        "price": price,
        "link": clean_link,
        "year": year,
        "mileage": mileage,
        "caixa": caixa
    }


# ============================================================
# SCRAPE ARTICLES
# ============================================================

def scrape_articles(
    soup,
    detail_cache
):

    if soup is None:
        return []

    cards = find_cards(
        soup
    )

    results = []

    seen_links = set()

    # --------------------------------------------------------
    # First parse all search cards
    # --------------------------------------------------------

    for card in cards:

        result = parse_search_card(
            card
        )

        if result is None:
            continue

        link = result["link"]

        if link in seen_links:
            continue

        seen_links.add(
            link
        )

        results.append(
            result
        )

    # ========================================================
    # FIND ADS THAT NEED DETAIL PAGES
    # ========================================================

    ads_needing_details = []

    for item in results:

        if (
            item["year"] is None
            or
            item["mileage"] is None
            or
            item["caixa"] == "N/A"
        ):

            if item["link"] not in detail_cache:

                ads_needing_details.append(
                    item["link"]
                )

    # ========================================================
    # FETCH DETAIL PAGES CONCURRENTLY
    # ========================================================

    if ads_needing_details:

        with ThreadPoolExecutor(
            max_workers=MAX_DETAIL_WORKERS
        ) as executor:

            future_to_url = {
                executor.submit(
                    fetch_ad_page,
                    url
                ): url
                for url in ads_needing_details
            }

            for future in as_completed(
                future_to_url
            ):

                url = future_to_url[
                    future
                ]

                try:

                    ad_soup = future.result()

                    if ad_soup:

                        detail_cache[
                            url
                        ] = parse_ad_details(
                            ad_soup
                        )

                    else:

                        detail_cache[
                            url
                        ] = (
                            None,
                            None,
                            "N/A"
                        )

                except Exception:

                    detail_cache[
                        url
                    ] = (
                        None,
                        None,
                        "N/A"
                    )

    # ========================================================
    # MERGE DETAIL DATA
    # ========================================================

    for item in results:

        link = item["link"]

        if link in detail_cache:

            detail_year, detail_mileage, detail_caixa = (
                detail_cache[link]
            )

            # Only replace missing values
            if item["year"] is None:
                item["year"] = detail_year

            if item["mileage"] is None:
                item["mileage"] = detail_mileage

            if item["caixa"] == "N/A":
                item["caixa"] = detail_caixa

        # ----------------------------------------------------
        # Title fallback
        # ----------------------------------------------------

        title_lower = item["title"].lower()

        if item["year"] is None:

            match = re.search(
                r"\b(?:ano|year)\s*:?\s*(\d{4})\b",
                title_lower,
                re.IGNORECASE
            )

            if match:

                candidate = int(
                    match.group(1)
                )

                if 1900 <= candidate <= 2100:
                    item["year"] = candidate

        if item["mileage"] is None:

            item["mileage"] = parse_mileage(
                item["title"]
            )

        # ----------------------------------------------------
        # Gearbox title fallback
        # ----------------------------------------------------

        if item["caixa"] == "N/A":

            if any(
                keyword in title_lower
                for keyword in AUTO_KEYWORDS
            ):

                item["caixa"] = "Automático"

            elif any(
                keyword in title_lower
                for keyword in MANUAL_KEYWORDS
            ):

                item["caixa"] = "Manual"

    return results


# ============================================================
# PRINT RESULTS
# ============================================================

def print_results(results):

    numeric_prices = [
        item["price"]
        for item in results
        if item["price"] is not None
    ]

    avg_price = (
        sum(numeric_prices)
        /
        len(numeric_prices)
        if numeric_prices
        else 0
    )

    print(
        Fore.CYAN +
        f"\n--- Displaying "
        f"{len(results)} Final Results "
        f"(Avg Price: {avg_price:.2f}€) ---\n" +
        Style.RESET_ALL
    )

    if not results:

        print(
            Fore.YELLOW +
            "No results to display after filtering." +
            Style.RESET_ALL
        )

        return

    for i, item in enumerate(
        results,
        1
    ):

        price = item["price"]

        price_display = (
            f"{price:.2f}€"
            if price is not None
            else "N/A"
        )

        year_display = (
            int(item["year"])
            if item["year"] is not None
            else "N/A"
        )

        mileage_display = (
            f"{item['mileage']:,} km"
            if item["mileage"] is not None
            else "N/A"
        )

        caixa_display = (
            item["caixa"]
            if item["caixa"]
            else "N/A"
        )

        numeric_price = (
            float(price)
            if price is not None
            else avg_price
        )

        color = (
            Fore.RED
            if numeric_price > avg_price
            else Fore.GREEN
        )

        print(
            color +
            f"{i}. {item['title']} - "
            f"{price_display}" +
            Style.RESET_ALL
        )

        print(
            Fore.WHITE +
            f"   Details: "
            f"Year: {year_display} | "
            f"Mileage: {mileage_display} | "
            f"Caixa: {caixa_display}"
        )

        print(
            Fore.YELLOW +
            f"   {item['link']}" +
            Style.RESET_ALL
        )


# ============================================================
# SORT
# ============================================================

def sort_results(results):

    return sorted(
        results,
        key=lambda x:
        x["price"]
        if x["price"] is not None
        else float("inf")
    )


# ============================================================
# EXPORT XLSX
# ============================================================

def export_results_xlsx(
    results,
    filename="olx_search_results.xlsx"
):

    if not results:

        print(
            Fore.YELLOW +
            "No data to export." +
            Style.RESET_ALL
        )

        return

    df = pd.DataFrame(
        results
    )

    df.rename(
        columns={
            "title": "Título do Anúncio",
            "price": "Preço (€)",
            "link": "Link do Anúncio",
            "year": "Ano",
            "mileage": "Quilómetros (km)",
            "caixa": "Caixa (Gearbox)"
        },
        inplace=True
    )

    df["Preço (€)"] = (
        df["Preço (€)"]
        .round(2)
    )

    df["Ano"] = df["Ano"].apply(
        lambda x:
        int(x)
        if pd.notna(x) and x > 0
        else None
    )

    df["Quilómetros (km)"] = (
        df["Quilómetros (km)"]
        .apply(
            lambda x:
            int(x)
            if pd.notna(x) and x > 0
            else None
        )
    )

    try:

        df.to_excel(
            filename,
            index=False,
            engine="openpyxl"
        )

        print(
            Fore.CYAN +
            f"\nSuccessfully exported "
            f"{len(results)} results to "
            f"{filename}" +
            Style.RESET_ALL
        )

    except Exception as e:

        print(
            Fore.RED +
            f"\nError during Excel export: "
            f"{e}" +
            Style.RESET_ALL
        )


# ============================================================
# RUN SEARCH
# ============================================================

def run_search():

    search_query = input(
        Fore.GREEN +
        "Search for: "
    ).replace(
        " ",
        "-"
    )

    page_limit = 10
    current_page = 1

    # Cache individual ad information
    detail_cache = {}

    # ========================================================
    # SESSION FOR SEARCH PAGES
    # ========================================================

    with requests.Session() as session:

        # ----------------------------------------------------
        # FIRST PAGE
        # ----------------------------------------------------

        soup = fetch_page(
            session,
            search_query,
            current_page
        )

        if soup is None:

            print(
                Fore.RED +
                "Could not fetch the first page. "
                "Aborting search." +
                Style.RESET_ALL
            )

            return

        # ----------------------------------------------------
        # TOTAL PAGES
        # ----------------------------------------------------

        total_pages = get_total_pages(
            soup
        )

        print(
            Fore.MAGENTA +
            f"\nTotal pages found: "
            f"{total_pages}\n"
        )

        # ----------------------------------------------------
        # FIRST PAGE
        # ----------------------------------------------------

        all_results = scrape_articles(
            soup,
            detail_cache
        )

        print(
            Fore.GREEN +
            f"Loaded "
            f"{len(all_results)} "
            f"results from page 1."
        )

        # ====================================================
        # ADDITIONAL SEARCH PAGES
        # ====================================================

        while current_page < total_pages:

            delay = random.uniform(
                1.5,
                3.0
            )

            print(
                Fore.LIGHTBLACK_EX +
                f"\nPausing for "
                f"{delay:.2f}s..."
            )

            time.sleep(
                delay
            )

            start_page = (
                current_page + 1
            )

            end_page = min(
                current_page + page_limit,
                total_pages
            )

            print(
                Fore.BLUE +
                f"\nFetching pages "
                f"{start_page} to "
                f"{end_page}...\n"
            )

            for page in range(
                start_page,
                end_page + 1
            ):

                soup = fetch_page(
                    session,
                    search_query,
                    page
                )

                if soup is not None:

                    page_results = scrape_articles(
                        soup,
                        detail_cache
                    )

                    all_results.extend(
                        page_results
                    )

                    print(
                        Fore.LIGHTBLACK_EX +
                        f"Page {page}: "
                        f"{len(page_results)} "
                        f"listings found."
                    )

                current_page = page

            print(
                Fore.GREEN +
                f"\nLoaded "
                f"{len(all_results)} "
                f"results so far "
                f"(up to page "
                f"{current_page}).\n"
            )

            if current_page >= total_pages:
                break

            choice = input(
                "Load 10 more pages? "
                "(yes/no): "
            ).strip().lower()

            if choice != "yes":
                break

    # ========================================================
    # SORT
    # ========================================================

    sort_choice = input(
        "\nSort results by price? "
        "(yes/no): "
    ).strip().lower()

    if sort_choice == "yes":

        all_results = sort_results(
            all_results
        )

        print(
            Fore.GREEN +
            "Results sorted by price." +
            Style.RESET_ALL
        )

    # ========================================================
    # MIN PRICE
    # ========================================================

    min_price_input = input(
        "\nMinimum price to include "
        "(press Enter to skip): "
    ).strip()

    if min_price_input:

        min_price_value = parse_numeric(
            min_price_input
        )

        if min_price_value is not None:

            all_results = [
                item
                for item in all_results
                if (
                    item["price"] is not None
                    and
                    item["price"] >= min_price_value
                )
            ]

            print(
                Fore.GREEN +
                f"Filtered results above "
                f"{min_price_value:.2f}€." +
                Style.RESET_ALL
            )

    # ========================================================
    # MAX PRICE
    # ========================================================

    max_price_input = input(
        "\nMaximum price to include "
        "(press Enter to skip): "
    ).strip()

    if max_price_input:

        max_price_value = parse_numeric(
            max_price_input
        )

        if max_price_value is not None:

            all_results = [
                item
                for item in all_results
                if (
                    item["price"] is not None
                    and
                    item["price"] <= max_price_value
                )
            ]

            print(
                Fore.GREEN +
                f"Filtered results below "
                f"{max_price_value:.2f}€." +
                Style.RESET_ALL
            )
        min_year_input = input("\nMinimum year to include (press Enter to skip): ").strip()
    if min_year_input:
        try:
            min_year_value = int(min_year_input)
            all_results = [
                item for item in all_results
                if item['year'] is not None and item['year'] >= min_year_value
            ]
            print(
                Fore.GREEN
                + f"Filtered results from year {min_year_value} onwards."
                + Style.RESET_ALL
            )
        except ValueError:
            print(Fore.RED + "Invalid year. Year filter skipped." + Style.RESET_ALL)

    max_year_input = input("\nMaximum year to include (press Enter to skip): ").strip()
    if max_year_input:
        try:
            max_year_value = int(max_year_input)
            all_results = [
                item for item in all_results
                if item['year'] is not None and item['year'] <= max_year_value
            ]
            print(
                Fore.GREEN
                + f"Filtered results up to year {max_year_value}."
                + Style.RESET_ALL
            )
        except ValueError:
            print(Fore.RED + "Invalid year. Year filter skipped." + Style.RESET_ALL)
    # ========================================================
    # EXCLUDE WORD
    # ========================================================

    exclude_word = input(
        "\nExclude items containing this word "
        "(press Enter to skip): "
    ).strip().lower()

    if exclude_word:

        all_results = [
            item
            for item in all_results
            if exclude_word
            not in item["title"].lower()
        ]

        print(
            Fore.GREEN +
            f"Filtered results excluding "
            f"'{exclude_word}'." +
            Style.RESET_ALL
        )

    # ========================================================
    # DISPLAY
    # ========================================================

    print_results(
        all_results
    )

    # ========================================================
    # EXPORT
    # ========================================================

    export_choice = input(
        Fore.GREEN +
        "\nExport results to XLSX? "
        "(yes/no): "
    ).strip().lower()

    if export_choice == "yes":

        export_results_xlsx(
            all_results
        )


# ============================================================
# MAIN
# ============================================================

def main():

    while True:

        run_search()

        again = input(
            Fore.GREEN +
            "\nDo another search? "
            "(yes/no): "
        ).strip().lower()

        if again != "yes":

            print(
                Fore.YELLOW +
                "Goodbye!"
            )

            break


if __name__ == "__main__":
    main()
