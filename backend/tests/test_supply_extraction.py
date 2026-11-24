"""Supplier extraction on sentences quoted from NVIDIA's FY2026 10-K (genuine filing text).

A supplier relationship must never be inferred from a competitor list or a biography.
"""

from deepterminal_api.analysis.supply_chain import extract_relationships

OWN = {"nvidia", "corp"}


def rel(sentence):
    return {name: (role, country) for name, role, country in extract_relationships(sentence, OWN)}


def test_foundries_and_memory_suppliers_are_extracted():
    r = rel("We utilize foundries, such as Taiwan Semiconductor Manufacturing Company Limited, or TSMC, and "
            "Samsung Electronics Co., Ltd., or Samsung, to produce our semiconductor wafers.")
    assert r["Taiwan Semiconductor Manufacturing Company Limited"] == ("manufacturer", None)   # "Taiwan" is part of the name
    assert r["Samsung Electronics Co., Ltd."] == ("manufacturer", None)
    r = rel("We purchase memory from SK Hynix Inc., Micron Technology, Inc., and Samsung.")
    assert set(r) == {"SK Hynix Inc.", "Micron Technology, Inc."} and r["SK Hynix Inc."][0] == "supplier"
    r = rel("We engage with independent subcontractors and contract manufacturers such as Hon Hai Precision Industry "
            "Co., Ltd., Wistron Corporation, and Fabrinet to perform assembly, testing and packaging of our final products.")
    assert set(r) == {"Hon Hai Precision Industry Co., Ltd.", "Wistron Corporation"}


def test_competitor_lists_and_biographies_are_not_relationships():
    assert rel("Our current competitors include: • suppliers and licensors of hardware and software for discrete and "
               "integrated GPUs, custom chips and other accelerated computing solutions, including solutions offered "
               "for AI, such as Advanced Micro Devices, Inc., or AMD, Huawei Technologies Co.") == {}
    assert rel("• suppliers of hardware and software for SoC products that are used in servers or embedded into "
               "automobiles, autonomous machines, and gaming devices, such as Ambarella, Inc., AMD, Broadcom, Intel, "
               "Qualcomm Incorporated, Renesas Electronics Corporation, and Samsung, or companies with internal teams "
               "designing SoC products for their own products and services, such as Tesla, Inc.;") == {}
    assert rel("Huang was employed at LSI Logic Corporation, a computer chip manufacturer, where he held a variety of "
               "positions including as Director of Coreware.") == {}
    assert rel("She served from 2002 to 2004 as Senior Vice President and General Manager of the Electro-Optics "
               "business at Coherent, Inc., a manufacturer of commercial and scientific laser equipment.") == {}


def test_country_only_when_text_places_the_entity_there():
    r = rel("We purchase wafer fabrication from Formosa Precision Foundry Co., Ltd., located in Taiwan.")
    assert r["Formosa Precision Foundry Co., Ltd."] == ("manufacturer", "Taiwan")


def test_customer_concentration_ignores_geographic_aggregates():
    from deepterminal_api.analysis.demand import customer_concentration
    text = ("Revenue from sales to customers headquartered outside of the United States accounted for 31\n%,\n41\n%, "
            "and\n48\n% of total revenue for fiscal years 2026, 2025, and 2024, respectively. Direct Customers – For "
            "fiscal year 2026, sales to one direct customer represented\n22\n% of total revenue and sales to another "
            "direct customer represented\n14\n% of total revenue, all of which were primarily attributable to the "
            "Compute & Networking segment. For fiscal year 2025, sales to one direct customer represented 12% of total "
            "revenue and sales to two direct customers each represented 11% of total revenue.")
    got = {(x["fy"], x["share"]) for x in customer_concentration(text, 2026)}
    assert got == {(2026, 0.22), (2025, 0.12)}


def test_summary_compensation_table_real_layouts():
    from deepterminal_api.services.filings import compensation_table
    sp = "<td></td>" * 6
    html = f"""<table><tr>{sp}</tr>
      <tr><td>Named Executive and Principal Position</td><td>Year</td><td>Salary ($)</td><td>Bonus ($)</td>
          <td>Stock Awards (1) ($)</td><td>All Other Compensation ($)</td><td>Total ($)</td></tr>
      <tr><td>Jen-Hsun Huang</td><td>2026</td><td>$</td><td>1,497,627</td><td>—</td><td>30,000,000(2)</td>
          <td>$</td><td>36,343,830</td></tr>
      <tr><td>President and CEO</td><td>2025</td><td>$</td><td>1,486,199</td><td>—</td><td>40,000,000</td><td>$</td><td>49,866,251</td></tr>
      <tr><td>2024</td><td>996,514</td><td>—</td><td>30,000,000</td><td>34,167,902</td></tr>
      <tr><td>Colette M. Kress EVP and CFO</td><td>2026</td><td>898,577</td><td>0</td><td>13,000,000</td><td>14,340,850</td></tr>
    </table><table><tr><td>Base Salary: $3 million, total pay unchanged; stock award mix 25/75</td></tr></table>"""
    rows = compensation_table(html)
    assert [(r["name"], r["year"], r["total"]) for r in rows] == [
        ("Jen-Hsun Huang", 2026, 36343830.0), ("Jen-Hsun Huang", 2025, 49866251.0), ("Jen-Hsun Huang", 2024, 34167902.0),
        ("Colette M. Kress EVP and CFO", 2026, 14340850.0)]
    assert rows[1]["position"] == "President and CEO" and rows[0]["salary"] == 1497627.0


def test_mention_relations_on_real_sentences():
    # Sentences quoted from other filers' 10-Ks that name NVIDIA (EDGAR full-text search, 2026).
    from deepterminal_api.analysis.mentions import relation, search_phrase
    assert search_phrase("NVIDIA CORP") == "NVIDIA" and search_phrase("Apple Inc.") == "Apple Inc"
    r = lambda s: relation(s, "NVIDIA")
    assert r("We are substantially dependent on NVIDIA Corporation as a supplier of graphics processing units") \
        == "depends on it as a supplier"
    assert r("In July 2023, in connection with a private placement of shares of Class A common stock to NVIDIA "
             "Corporation, or NVIDIA, we entered into a Registration Rights Agreement") == "names it as an investor"
    assert r("Subsequent to June 30, 2025, we procured, through a combination of purchases and equipment leasing, "
             "approximately 5.5k NVIDIA B200 GPUs") == "depends on it as a supplier"
    assert r("We have made substantial progress in our collaboration efforts with NVIDIA") == "names it as a partner"
    assert r("Our competitors include NVIDIA, AMD and Intel") == "names it as a competitor"
