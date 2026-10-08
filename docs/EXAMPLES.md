# Example Q&A transcripts

The brief's six example questions, asked through `POST /ask` with `scripts/ask_examples.py` against
the committed snapshot (data as of 2026-10-07). Output is pasted unedited. `route` and `tools` come
from the tools the agent actually ran, not from the model's text.

Model: Google AI Studio free tier, via its OpenAI-compatible endpoint. The free tier allows about
20 requests per model per day, so the run was spread across `gemini-3.7-flash` and
`gemini-3.5-flash` (noted per question). The code and prompts were identical for every run.

## 1. What were NVDA's revenue and net income for the last three fiscal years?

`route: numbers   tools: get_fundamentals` · model `gemini-3.7-flash`

NVIDIA’s revenue and net income for the last three fiscal years were:

* **FY2024** (ended January 28, 2024):
  * **Revenue:** $60.92B
  * **Net Income:** $29.76B

* **FY2025** (ended January 26, 2025):
  * **Revenue:** $130.50B
  * **Net Income:** $72.88B

* **FY2026** (ended January 25, 2026):
  * **Revenue:** $215.94B
  * **Net Income:** $120.07B

## 2. Which of the five companies had the highest gross margin last year?

`route: numbers   tools: compare_companies` · model `gemini-3.7-flash`

**NVIDIA (NVDA)** had the highest gross margin in its latest fiscal year at **71.1%**.

Note that fiscal years end on different dates for each company:

1. **NVDA** (FY2026, period ended 2026-01-25): **71.1%**
2. **MSFT** (FY2026, period ended 2026-06-30): **67.9%**
3. **GOOGL** (FY2025, period ended 2025-12-31): **59.7%**
4. **AAPL** (FY2025, period ended 2025-09-27): **46.9%**
5. **ETN** (FY2025, period ended 2025-12-31): **37.6%**

## 3. What is AAPL's trailing P/E right now?

`route: numbers   tools: get_valuation` · model `gemini-3.7-flash`

Apple's (AAPL) trailing P/E is **45.1x**.

* **Latest Closing Price:** $336.67 (as of 2026-10-07)
* **Latest Annual Diluted EPS:** $7.46 (FY2025, year ended 2025-09-27)

## 4. What new risk factors did NVDA add in its latest 10-K versus the prior year?

`route: filings   tools: risk_factor_changes` · model `gemini-3.7-flash`

In its **FY2026 10-K** (compared to the FY2025 10-K), NVIDIA added several new risk factors and specific disclosures across the following areas:

---

### 1. China Export Controls, Foreclosure from China Data Center Market, and Product Charges
* **H20 Licensing Requirement & $4.5B Charge:** In April 2025, the U.S. government (USG) required export licenses for shipments of H20 integrated circuits (and equivalent bandwidth chips) to China/D:5 countries, causing demand to diminish and resulting in a **$4.5 billion charge** in Q1 FY2026 for excess inventory and purchase obligations.
* **H20 Licensing Revenue & USG Expectations:** In August 2025, the USG granted licenses to ship certain H20 products to select China-based customers (generating ~$60 million in revenue). USG officials expressed an uncodified expectation that the USG receive 15% or more of revenue from licensed sales.
* **H200 Licensing & Tariffs:** In February 2026, the USG granted a license to ship small amounts of H200 chips to specific China customers, requiring U.S. inspection and subjecting shipments to a **25% tariff** upon importation into the United States.
* **Effective Foreclosure from China Data Center Market:** NVIDIA stated that as of the end of FY2026, it is effectively foreclosed from competing in China’s data center computing market under current rules, which has helped competitors build larger developer and customer ecosystems to challenge NVIDIA globally.
* **Worldwide & Downstream Export Controls:** Expanded controls targeting AI GPUs and semiconductors could restrict downstream users, Cloud Service Providers (CSPs), and NVIDIA AI cloud services outside of China.

---

### 2. Commercial Arrangements, Counterparty Risks, and Financing Requests
* NVIDIA added risks concerning commercial arrangements, including long-term capacity purchase obligations and financial guarantees.
* The company noted it has been asked to offer financing arrangements to support customer and partner datacenter infrastructure buildouts (though it stated it has not entered into any financing arrangements). Such arrangements carry counterparty credit risk, project delays, and potential cash flow impacts.

---

### 3. IP License Agreement with Groq, Inc.
* NVIDIA disclosed that it entered into an intellectual property license arrangement with **Groq, Inc.** that required significant, nonrefundable payments.
* Risks include the significant engineering effort required to incorporate the technology into product roadmaps, potential delays or failure to achieve customer adoption, and the risk of failing to recover costs or realize an adequate return.

---

### 4. Constraints on Customer Datacenter Infrastructure: Energy, Capital, and Facilities
* NVIDIA highlighted risks regarding customers’ and partners’ ability to secure **energy, capital, and data center space** in a timely manner.
* Expanding power/energy capacity involves complex, multi-year regulatory and construction challenges, and capital constraints could slow AI infrastructure deployments.

---

### 5. Domestic (U.S.) Manufacturing Expansion
* NVIDIA noted it is increasing its U.S.-based manufacturing and investing in specialized domestic production equipment and processes, subject to risks of scaling delays, execution challenges, and the domestic ecosystem's capacity to ramp supply.

---

### 6. Strategic Investments and OpenAI Agreement
* **OpenAI Agreement:** NVIDIA disclosed that it is finalizing an investment and partnership agreement with **OpenAI**, noting there is no assurance that the agreement will be entered into or that a transaction will be completed.
* **Investment Portfolio Risks:** General risks around non-marketable, illiquid investments in early-stage ecosystem companies, portfolio industry sector concentration, and potential impairment losses.

---

### 7. AI-Enhanced Cyber-Attacks
* Added risks that threat actors, including nation-states and sophisticated organizations, are using AI technology to launch more automated, targeted, and coordinated cyber-attacks.

## 5. How did MSFT's revenue grow last year, and what did management attribute it to?

`route: both   tools: get_fundamentals, search_filings, search_filings` · model `gemini-3.5-flash`

In fiscal year 2026 (ended June 30, 2026), Microsoft’s revenue grew to **$331.84 billion** (reported as $331,839 million in the 10-K), representing a **17.8%** (or 18% rounded) increase year-over-year from $281.72 billion ($281,724 million) in FY2025.

In its FY2026 10-K MD&A, management attributed the overall revenue increase of $50.1 billion primarily to **growth in Microsoft Cloud**. 

The segment-level drivers and management's explanations include:

### 1. Intelligent Cloud (Revenue increased $31.5 billion or 30%)
* **Azure and other cloud services:** Grew **41%**, driven by demand for services across the platform with continued growth across all workloads.
* **Server products:** Grew **1%**, primarily driven by higher purchases of licenses running in multi-cloud environments, offset in part by the continued customer shift to the cloud.
* **Enterprise and partner services:** Grew **6%**, driven by growth in Enterprise Support Services.

### 2. Productivity and Business Processes (Revenue increased $19.2 billion or 16%)
* **Microsoft 365 Commercial products and cloud services:** Grew **16%**. Within this, Microsoft 365 Commercial cloud revenue grew 17%, driven by growth in revenue per user from Microsoft 365 Copilot and Microsoft 365 E5, alongside 6% seat growth (driven by small and medium businesses and frontline worker offerings).
* **Microsoft 365 Consumer products and cloud services:** Grew **24%**, with cloud revenue up 28% driven by growth in revenue per user and 7% subscriber growth.
* **LinkedIn:** Grew **11%**, with growth across all lines of business.
* **Dynamics products and cloud services:** Grew **15%**, driven by Dynamics 365 growth of 18% across all workloads.

### 3. More Personal Computing (Revenue decreased $597 million or 1%)
This segment partially offset overall growth due to declines in gaming and devices:
* **XBOX:** Revenue decreased **7%**, driven by a 29% decline in hardware revenue (lower console volumes) and a 5% decline in XBOX content and services (due to a strong prior-year comparable, offset in part by growth in XBOX Game Pass).
* **Windows and Devices:** Revenue decreased **1%**, driven by a decline in Devices, offset in part by 5% Windows OEM growth.
* **Search advertising:** Revenue (excluding traffic acquisition costs) increased **12%**, which partially offset the segment's overall decline.

## 6. What is the company's forward guidance for next quarter?

`route: none   tools: none` · model `gemini-3.7-flash`

Forward guidance, quarterly forecasts, and future quarterly outlooks are not available in the provided dataset. The available data is limited to historical annual SEC 10-K filings (reported financials, Item 1A Risk Factors, and Item 7 MD&A) and closing stock prices for Apple (AAPL), Eaton (ETN), Alphabet (GOOGL), Microsoft (MSFT), and NVIDIA (NVDA).

Instead, I can provide historical annual financial performance (such as revenue, net income, margins, and year-over-year growth), trailing P/E valuations, or management's discussion of past performance and risk factors from their annual 10-K reports. Please let me know which company and historical metrics you would like to examine.
