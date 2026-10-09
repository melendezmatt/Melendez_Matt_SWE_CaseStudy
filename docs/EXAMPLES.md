# Example Q&A transcripts

The brief's six example questions, asked through `POST /ask` with `scripts/ask_examples.py` against
the committed snapshot (data as of 2026-10-07). Output is pasted unedited. `route` and `tools` come
from the tools the agent actually ran, not from the model's text.

Model: Google AI Studio free tier, `gemini-3.7-flash`, via its OpenAI-compatible endpoint. Run on
2026-10-08 with the current code: unit-aware number checking, the period-alignment note in
company comparisons, and linked `source_refs` (not shown here; see the API response). No answer
had a figure the number check couldn't find in the tool results.

## 1. What were NVDA's revenue and net income for the last three fiscal years?

`route: numbers   tools: get_fundamentals` · model `gemini-3.7-flash`

NVIDIA's revenue and net income for the last three fiscal years are:

* **FY2026** (ended January 25, 2026):
  * **Revenue:** $215.94B
  * **Net Income:** $120.07B

* **FY2025** (ended January 26, 2025):
  * **Revenue:** $130.50B
  * **Net Income:** $72.88B

* **FY2024** (ended January 28, 2024):
  * **Revenue:** $60.92B
  * **Net Income:** $29.76B

## 2. Which of the five companies had the highest gross margin last year?

`route: numbers   tools: compare_companies` · model `gemini-3.7-flash`

**NVIDIA (NVDA)** had the highest gross margin last year (in its latest fiscal year) at **71.1%**.

Note that fiscal year-end dates differ across the five companies (spanning up to 276 days apart):

1. **NVDA**: 71.1% (FY2026 ended 2026-01-25)
2. **MSFT**: 67.9% (FY2026 ended 2026-06-30)
3. **GOOGL**: 59.7% (FY2025 ended 2025-12-31)
4. **AAPL**: 46.9% (FY2025 ended 2025-09-27)
5. **ETN**: 37.6% (FY2025 ended 2025-12-31)

## 3. What is AAPL's trailing P/E right now?

`route: numbers   tools: get_valuation` · model `gemini-3.7-flash`

Apple's (AAPL) trailing P/E is **45.1x**.

* **Latest Close Price:** $336.67 (as of 2026-10-07)
* **Latest Annual Diluted EPS:** $7.46 (FY2025, year ended 2025-09-27)

## 4. What new risk factors did NVDA add in its latest 10-K versus the prior year?

`route: filings   tools: risk_factor_changes, risk_factor_changes` · model `gemini-3.7-flash`

In its **FY2026 10-K** (compared to the FY2025 10-K), NVIDIA added **31 new risk factor paragraphs** (along with 28 rewritten and 20 removed paragraphs). 

The primary new risk factors added cover the following key areas:

---

### 1. AI Infrastructure, Energy, and Capital Constraints
* **Energy, Datacenter, and Capital Shortages:** NVIDIA added a new risk noting that the availability of data centers, energy, and capital to support customer and partner buildouts of NVIDIA AI infrastructure is critical. It emphasized that expanding energy capacity is a complex, multi-year process with regulatory, technical, and construction challenges, and capital constraints could delay customer deployments or reduce the scale of AI adoption.

### 2. Strategic Transactions & Partnerships
* **OpenAI Investment and Partnership:** NVIDIA disclosed: *"We are finalizing an investment and partnership agreement with OpenAI. There is no assurance that we will enter into an investment and partnership agreement with OpenAI or that a transaction will be completed."*
* **Groq IP Licensing Agreement:** NVIDIA disclosed that it entered into an intellectual property license arrangement with **Groq, Inc.** that required significant nonrefundable payments, citing risks that integrating the technology into product roadmaps may be delayed, unsuccessful, or fail to achieve commercial returns.

### 3. Customer Financing and Counterparty Risks
* **Datacenter Financing and Guarantees:** NVIDIA added risks regarding commercial arrangements—including long-term capacity purchase obligations and financial guarantees—and noted it has been asked to offer financing arrangements to support customer datacenter buildouts (though it had not entered into financing arrangements to date). These arrangements expose the company to counterparty risk, project delays, distress, or credit risk.

### 4. U.S. Export Controls, Tariffs, and China Market Foreclosure
NVIDIA substantially expanded its disclosures regarding U.S. government (USG) export controls and China:
* **H20 License Requirements & $4.5 Billion Inventory Charge:** In April 2025, the USG required licenses for exports of H20 chips to China/D:5 countries, resulting in a **$4.5 billion charge** in Q1 FY2026 for excess inventory and purchase obligations. In August 2025, licenses were granted under which NVIDIA generated ~$60 million in H20 revenue, with USG officials expressing an expectation to receive 15% or more of revenue generated from licensed sales (unaccompanied by codified regulations).
* **H200 Licensing and 25% U.S. Tariff:** In February 2026, the USG granted a license to ship small amounts of H200 products to specific China-based customers requiring U.S. inspection, subjecting shipments to a **25% tariff** upon importation into the U.S.
* **Effective Foreclosure from China Data Center Market:** NVIDIA stated that as of the end of FY2026, it was *"effectively foreclosed from competing in China's data center computing/compute market,"* which has helped competitors build larger developer and customer ecosystems to challenge NVIDIA worldwide.
* **Regulatory Changes and the GAIN AI Act:** Management noted the USG announced in May 2025 it would rescind the AI Diffusion Interim Final Rule (IFR) and implement a replacement rule, and highlighted the Senate's passage in October 2025 of the "GAIN AI Act" in the NDAA.
* **Open-Source Chinese Models:** Added risks concerning potential regulatory controls limiting NVIDIA's ability to support applications built on Chinese foundation models, specifically naming **DeepSeek, Qwen, and KIMMI**.
* **Chip Tracking / Throttling Mandates:** USG proposals or conditions requiring chip tracking and throttling mechanisms, as well as China’s government questioning whether H20 chips contain built-in vulnerabilities.
* **Export Control Compliance Allegations:** Risks that unsubstantiated allegations claiming NVIDIA complies with the letter but not the "spirit" of export controls, or exploits supposed "loopholes," could harm reputation and customer relationships.

### 5. Domestic Manufacturing Scaling
* **U.S.-Based Manufacturing Expansion:** NVIDIA noted it is increasing U.S.-based manufacturing and investing in specialized equipment and processes, exposing it to risks of delays, scaling challenges, and reliance on the domestic manufacturing ecosystem's capacity.

### 6. Investment Portfolio Risks
* **Concentration in Ecosystem Investments:** Added risks regarding industry sector concentration within its investment portfolio, noting that declines in specific sectors could increase impairment losses from investments in private and early-stage companies.

## 5. How did MSFT's revenue grow last year, and what did management attribute it to?

`route: both   tools: get_fundamentals, search_filings` · model `gemini-3.7-flash`

In its latest fiscal year (FY2026, ended June 30, 2026), Microsoft's revenue was **$331.84B**, representing year-over-year growth of **17.8%** (compared to $281.72B in FY2025). 

In the FY2026 10-K MD&A, management highlighted that total **Microsoft Cloud revenue increased 27% to $214.4 billion**. Revenue performance across segments was driven by the following:

---

### 1. Intelligent Cloud
**Revenue increased $31.5 billion (30%)**, driven by:
* **Server products and cloud services:** Increased $31.0 billion (31%), led by **Azure and other cloud services**, which grew **41%** due to demand for services across the platform with continued growth across all workloads.
* **Server products:** Increased 1%, driven by higher purchases of licenses running in multi-cloud environments, offset in part by the customer shift to cloud.
* **Enterprise and partner services:** Increased $500 million (6%), driven by growth in Enterprise Support Services.

---

### 2. Productivity and Business Processes
**Revenue increased $19.2 billion (16%)** (including a favorable 2% foreign currency impact), driven by:
* **Microsoft 365 Commercial products and cloud services:** Increased $14.2 billion (16%).
  * **Microsoft 365 Commercial cloud** grew 17%, driven by growth in revenue per user (spurred by Microsoft 365 Copilot and Microsoft 365 E5) and commercial seat growth of 6% (driven by small and medium businesses and frontline worker offerings).
  * **Microsoft 365 Commercial products** grew 13%, driven by growth in the Windows Commercial on-premises components of Microsoft 365 suite sales and an increase in Office 2024 transactional purchasing.
* **Microsoft 365 Consumer products and cloud services:** Increased $1.8 billion (24%), with cloud revenue growing 28% from higher revenue per user and subscriber growth of 7%.
* **LinkedIn:** Increased $2.0 billion (11%), with growth across all lines of business.
* **Dynamics products and cloud services:** Increased $1.2 billion (15%), driven by 18% growth in Dynamics 365 across all workloads.

---

### 3. More Personal Computing
**Revenue decreased $597 million (1%)**, reflecting:
* **XBOX revenue:** Decreased $1.7 billion (7%), driven by:
  * A 29% decline in XBOX hardware revenue due to lower console sales volume.
  * A 5% decline in XBOX content and services revenue against a prior-year comparable that benefited from strong first-party content, offset in part by growth in XBOX Game Pass.
* **Windows and Devices:** Decreased $230 million (1%), as device declines were partially offset by 5% growth in Windows OEM.
* **Search advertising:** Partially offset these declines, increasing $1.3 billion (9%), or 12% excluding traffic acquisition costs, driven by higher search volume, revenue per search, and third-party partnerships.

## 6. What is the company's forward guidance for next quarter?

`route: none   tools: none` · model `gemini-3.7-flash`

Forward guidance and next-quarter outlook are not available. The available data is strictly from annual SEC 10-K filings (MD&A and Risk Factors), reported annual financial metrics, and daily closing prices for covered companies (AAPL, ETN, GOOGL, MSFT, and NVDA).

Instead, I can provide:
- Reported historical annual financials (revenue, gross profit, operating income, net income, diluted EPS, margins, and year-over-year growth)
- Trailing P/E valuations
- Management discussion and analysis (MD&A) of past annual performance and drivers
- Item 1A Risk Factors disclosures and year-over-year risk changes

If you have a specific covered company and historical metric or filing topic in mind, please let me know!
