# Fontina PDO Traceability Platform — Green Blockchain

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Paper](https://img.shields.io/badge/Paper-10.3390%2Fsu14063321-blue)](https://doi.org/10.3390/su14063321)
[![Journal](https://img.shields.io/badge/Journal-Sustainability_(MDPI)-green)](https://www.mdpi.com/journal/sustainability)
[![Blockchain](https://img.shields.io/badge/Blockchain-Algorand-black)](https://www.algorand.com/)
[![Framework](https://img.shields.io/badge/Backend-Django-092E20?logo=django)](https://www.djangoproject.com/)
[![EU Project](https://img.shields.io/badge/EU_Project-Typicalp-003399)](https://www.progetti.interreg-italiasvizzera.eu/it/b/78/typicalp)

---

## Overview

This repository contains the partial source code, data model, and documentation of the traceability platform described in:

> **Varavallo, G., Caragnano, G., Bertone, F., Vernetti-Prot, L., & Terzo, O. (2022).** *Traceability Platform Based on Green Blockchain: An Application Case Study in Dairy Supply Chain.* Sustainability, 14(6), 3321. https://doi.org/10.3390/su14063321

The platform digitizes and guarantees the immutability of the entire **Fontina PDO cheese supply chain** — from mountain pasture milk collection to consumer sale — by integrating a Django web application with the **Algorand blockchain** (Pure Proof-of-Stake), achieving minimal energy consumption and transaction costs below $0.01 USD.

The project was developed at [LINKS Foundation](https://linksfoundation.com) (Turin, Italy) as part of the EU-funded **Typicalp** Interreg project, in collaboration with the [Institut Agricole Régional (IAR)](https://www.iaraosta.it) of Aosta Valley.

---

## Research Context

The Fontina PDO supply chain involves six categories of operators across the Aosta Valley region (Italy): farmers, transporters, dairies, seasoning operators, packaging operators, and the Fontina Protection Consortium (CTF). Prior to this platform, information beyond the milk collection phase was recorded manually on paper, making real-time traceability and data immutability impossible.

This platform addresses those gaps by:
- Digitizing all five supply chain phases end-to-end
- Anchoring supply chain data to the Algorand blockchain at the packaging phase
- Generating a scannable QR Code for each cheese lot, linking consumers to the full production history

---

## Supply Chain Phases

```
Mountain Pasture                                                    Consumer
     │
     ▼
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐    ┌────────┐
│ Milk Production │───▶│  Processing  │───▶│  Seasoning  │───▶│ Packaging  │───▶│ Sales  │
│  (transporter)  │    │  (dairy op.) │    │  (≥3 months)│    │ + QR Code  │    │  + DLT │
└─────────────────┘    └──────────────┘    └─────────────┘    └────────────┘    └────────┘
                                                                      │
                                                            Data sent to Algorand
                                                            Blockchain (JSON txn)
```

All intermediate data is stored in MySQL (AWS). At the packaging stage, a single aggregated JSON transaction is submitted to the Algorand blockchain, minimizing both cost and energy impact.

---

## Architecture

The platform is built on three layers:

| Layer | Technology | Purpose |
|---|---|---|
| Back-end framework | Django (Python) | Web application, operator interfaces, business logic |
| Relational database | MySQL on AWS | Storage of all supply chain records |
| Distributed ledger | Algorand (Pure PoS) | Immutability, transparency, QR Code generation |

### Why Algorand?

Algorand uses the **Pure Proof-of-Stake (PPoS)** consensus mechanism via a Verifiable Random Function (VRF), which:
- Validates transactions in a few seconds
- Requires minimal computational power (no mining)
- Costs ~0.001 ALGO per transaction (< $0.01 USD as of 2022)
- Is fully carbon-neutral

This makes it uniquely suited for small local PDO supply chains where transaction costs and environmental impact are critical constraints.

---

## Data Model

The Django application is organized around six core models, each corresponding to a supply chain phase:

```
Milk_Productions ──────────────────────────────────────────────┐
     │                                                          │
     ├──▶ MilkImages          (receipt photos per collection)   │
     │                                                          │
     └──▶ MainProcessing ─────────────────────────────┐        │
               │                                       │        │
               ├──▶ SubProcessing   (per-vat details)  │        │
               │                                       │        │
               └──▶ Seasoning ──────────────────────┐  │        │
                         │                          │  │        │
                         ├──▶ Classifica            │  │        │
                         │   (CTF branding audit)   │  │        │
                         │                          │  │        │
                         └──▶ Packaging ────────────┘  │        │
                                   │                   │        │
                                   └──▶ Blockchain_    │        │
                                        transactions ──┘        │
                                        (Algorand txn)          │
                                                                │
Milk_analysis ──────────────────────────────────────────────────┘
(fat, protein, lactose, casein, somatic cell count per batch)
```

### Key models

**`Milk_Productions`** — records each milk collection run: total volume (L), farm type (mountain pasture / valley), date, and morning/evening slot.

**`MainProcessing`** — links a milk production batch to a seasoning lot; records cheese type, number of forms, casein number range, and CTF code.

**`Seasoning`** — tracks the maturation phase: start/end dates, warehouse location, number of forms branded by CTF, lot ID.

**`Classifica`** — records the CTF quality audit: forms evaluated, branded, and downgraded per lot.

**`Packaging`** — triggers the blockchain transaction; records packaging date, shelf life, and generates the QR Code linking to the Algorand explorer.

**`Blockchain_transactions`** — stores the Algorand transaction ID, lot reference, and validation status for each packaged batch.

---

## Algorand Integration

Data is submitted to the Algorand blockchain as an **Advanced Transaction** with a JSON payload in the `note` field, containing the aggregated supply chain record for a given packaging event.

The integration uses the [Algorand Python SDK](https://github.com/algorand/py-algorand-sdk) (`algosdk`):

```python
from algosdk.v2client import algod
from algosdk import mnemonic, transaction

# Initialize Algorand client
algod_address = 'https://testnet-algorand.api.purestake.io/ps2'
algodclient = algod.AlgodClient(algod_token, algod_address, headers)

# Build and sign transaction with JSON payload in note field
params = algodclient.suggested_params()
tx = transaction.PaymentTxn(
    sender, params.min_fee, params.first, params.last,
    params.gh, receiver, amount,
    note=json.dumps(supply_chain_data).encode(),
    flat_fee=True
)
signed_tx = tx.sign(account_private_key)
algodclient.send_transaction(signed_tx)
```

Each operator holds an individual Algorand wallet. Data is queried once across all phases at packaging time and submitted as a single transaction — keeping costs and energy consumption minimal. A verified example transaction is available on the [Algorand Explorer](https://algoexplorer.io/tx/Y4MTZNRYYD3ZAAG2XY6YIX6UKOWWNJNLKRCIPQ6KKLXM3QXLB5GQ).

---

## Repository Structure

```
fontina-blockchain-traceability/
├── README.md
├── LICENSE
├── docs/
│   └── paper_su14063321.pdf          # Published paper (open access)
├── platform/
│   ├── models.py                     # Django data model (all supply chain phases)
│   ├── algorand_integration.py       # Algorand SDK transaction logic
│   └── sample_transaction.json       # Example JSON payload sent to blockchain
├── data/
│   └── sample_dataset.csv            # Anonymized sample dataset
└── figures/
    ├── architecture.png              # High-level platform architecture
    └── supply_chain_flow.png         # Fontina PDO production chain
```

---

## Requirements

```
Python >= 3.8
Django >= 3.2
algosdk >= 1.4.0
mysqlclient
Pillow                  # for MilkImages
boto3                   # for AWS S3 image storage (optional)
```

> **Note on algosdk >= 1.4.0**: Starting from version 1.4.0, `flat_fee=True` must be explicitly set in `PaymentTxn` to avoid a fee calculation bug. The `content-type` header is no longer required when calling `send_transaction`.

---

## Sample Data

The `data/` directory contains an anonymized sample dataset with simulated supply chain records across all five phases, suitable for testing the data model and exploring the platform structure without access to the live system.

---

## Citation

If you use this code or find this work useful, please cite:

```bibtex
@article{varavallo2022traceability,
  title     = {Traceability Platform Based on Green Blockchain:
               An Application Case Study in Dairy Supply Chain},
  author    = {Varavallo, Giuseppe and Caragnano, Giuseppe and
               Bertone, Fabrizio and Vernetti-Prot, Luca and Terzo, Olivier},
  journal   = {Sustainability},
  volume    = {14},
  number    = {6},
  pages     = {3321},
  year      = {2022},
  publisher = {MDPI},
  doi       = {10.3390/su14063321}
}
```

---

## Authors

**Giuseppe Varavallo** — LINKS Foundation, Turin
✉ giuseppe.varavallo@linksfoundation.com

**Giuseppe Caragnano** — LINKS Foundation, Turin

**Fabrizio Bertone** — LINKS Foundation, Turin

**Luca Vernetti-Prot** — Institut Agricole Régional (IAR), Aosta

**Olivier Terzo** — LINKS Foundation, Turin

---

## Funding

This research was supported by the **TYPICALP** project — *"TYPicity, Innovation, competitiveness in Alpine dairy Products"* — Interreg Italy-Switzerland, Project ID: 493717.

---

## License

This work is licensed under the [Creative Commons Attribution 4.0 International License (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
