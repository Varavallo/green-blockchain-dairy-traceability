"""
algorand_integration.py — Fontina PDO Traceability Platform
============================================================
Handles the submission of supply chain data to the Algorand blockchain
as an Advanced Transaction with a JSON payload in the note field.

This module is called once per packaging event, aggregating all linked
supply chain phases (milk production → processing → seasoning → packaging)
into a single transaction to minimize cost and energy consumption.

Transaction cost:  ~0.001 ALGO (< $0.01 USD) per packaging lot
Consensus:         Pure Proof-of-Stake (PPoS) via Verifiable Random Function
Confirmation time: ~3.5 seconds

SDK requirement:   algosdk >= 2.0  (pip install py-algorand-sdk)

Reference:
    Varavallo et al. (2022). Traceability Platform Based on Green Blockchain:
    An Application Case Study in Dairy Supply Chain.
    Sustainability, 14(6), 3321. https://doi.org/10.3390/su14063321
"""

import json
import logging
import os
from base64 import b64decode
from dataclasses import dataclass
from typing import Optional

from algosdk import mnemonic, transaction
from algosdk.error import AlgodHTTPError
from algosdk.v2client import algod

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Load sensitive values from environment variables — never hardcode credentials.
# For local development, set these in a .env file and load with python-dotenv.
#
# Required environment variables:
#   ALGORAND_NODE_ADDRESS   e.g. https://testnet-api.algonode.cloud
#   ALGORAND_API_KEY        your PureStake / AlgoNode / custom node API key
#   ALGORAND_MNEMONIC       25-word mnemonic of the operator's Algorand wallet
#   ALGORAND_RECEIVER       public address of the Fontina Consortium wallet
# ---------------------------------------------------------------------------

ALGOD_ADDRESS  = os.environ.get("ALGORAND_NODE_ADDRESS", "https://testnet-api.algonode.cloud")
ALGOD_TOKEN    = os.environ.get("ALGORAND_API_KEY", "")
MNEMONIC       = os.environ.get("ALGORAND_MNEMONIC", "")
RECEIVER       = os.environ.get("ALGORAND_RECEIVER", "")

# Note field limit enforced by the Algorand protocol: 1024 bytes
NOTE_MAX_BYTES = 1024

# Minimum transaction amount in microALGOs (0 is valid for note-only txns)
TXN_AMOUNT_MICROALGOS = 0


# ---------------------------------------------------------------------------
# Client initialisation
# ---------------------------------------------------------------------------

def get_algod_client() -> algod.AlgodClient:
    """
    Initialise and return an Algorand v2 client.

    Supports both PureStake-style API key headers and open nodes
    (e.g. AlgoNode testnet/mainnet) that require no key.

    Returns:
        algod.AlgodClient: configured Algorand client.
    """
    headers = {"X-API-Key": ALGOD_TOKEN} if ALGOD_TOKEN else {}
    client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS, headers)
    logger.debug("Algorand client initialised — node: %s", ALGOD_ADDRESS)
    return client


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AlgorandTxnResult:
    """
    Result of a submitted Algorand transaction.

    Attributes:
        txid:            Algorand transaction ID (base32 string).
        confirmed_round: Block round in which the transaction was confirmed.
        note_decoded:    The JSON payload decoded from the confirmed note field.
    """
    txid:            str
    confirmed_round: int
    note_decoded:    Optional[dict] = None


# ---------------------------------------------------------------------------
# Core transaction function
# ---------------------------------------------------------------------------

def submit_supply_chain_data(supply_chain_payload: dict) -> AlgorandTxnResult:
    """
    Submit aggregated Fontina PDO supply chain data to the Algorand blockchain.

    The entire supply chain record (milk production → processing → seasoning
    → packaging) is serialised as JSON and stored in the transaction note field
    (max 1 KB). Data is sent only once, at the packaging phase, to keep
    transaction costs and energy consumption minimal.

    Args:
        supply_chain_payload: Dictionary containing all traceable supply chain
                              fields for a given packaging lot. Example structure
                              is shown in sample_transaction.json.

    Returns:
        AlgorandTxnResult with the confirmed transaction ID and round.

    Raises:
        ValueError:      If the JSON payload exceeds the 1 KB note field limit,
                         or if required environment variables are missing.
        AlgodHTTPError:  If the Algorand node rejects the transaction.
        Exception:       On unexpected SDK or network errors.

    Example:
        >>> payload = build_payload_from_packaging(packaging_id="abc-123")
        >>> result  = submit_supply_chain_data(payload)
        >>> print(result.txid)
        'Y4MTZNRYYD3ZAAG2XY6YIX6UKOWWNJNLKRCIPQ6KKLXM3QXLB5GQ'
    """
    # --- Validate environment -----------------------------------------------
    if not MNEMONIC:
        raise ValueError("ALGORAND_MNEMONIC environment variable is not set.")
    if not RECEIVER:
        raise ValueError("ALGORAND_RECEIVER environment variable is not set.")

    # --- Encode payload into bytes ------------------------------------------
    note_bytes = json.dumps(supply_chain_payload, ensure_ascii=False).encode("utf-8")

    if len(note_bytes) > NOTE_MAX_BYTES:
        raise ValueError(
            "Payload exceeds the Algorand note field limit "
            f"({len(note_bytes)} bytes > {NOTE_MAX_BYTES} bytes). "
            "Consider reducing the number of fields or splitting into multiple transactions."
        )

    # --- Recover account keys from mnemonic ---------------------------------
    private_key = mnemonic.to_private_key(MNEMONIC)
    public_key  = mnemonic.to_public_key(MNEMONIC)

    # --- Build transaction --------------------------------------------------
    client = get_algod_client()
    params = client.suggested_params()
    # Use flat fee = minimum fee (~0.001 ALGO). This avoids the fee scaling
    # with payload size that the default per-byte mode would apply.
    params.flat_fee = True
    params.fee      = params.min_fee

    unsigned_txn = transaction.PaymentTxn(
        sender   = public_key,
        sp       = params,           # passes first/last valid round, genesis hash, fee
        receiver = RECEIVER,
        amt      = TXN_AMOUNT_MICROALGOS,
        note     = note_bytes,
    )

    # --- Sign and submit ----------------------------------------------------
    signed_txn = unsigned_txn.sign(private_key)
    txid       = signed_txn.transaction.get_txid()

    logger.info("Submitting transaction to Algorand — txid: %s", txid)

    try:
        client.send_transaction(signed_txn)
    except AlgodHTTPError as exc:
        logger.error("Algorand node rejected transaction: %s", exc)
        raise

    # --- Wait for confirmation (built-in since algosdk >= 2.0) -------------
    # wait_rounds=4 means: wait at most 4 block rounds (~16 s) before raising.
    txn_result = transaction.wait_for_confirmation(client, txid, wait_rounds=4)
    confirmed_round = txn_result.get("confirmed-round", 0)

    logger.info(
        "Transaction confirmed in round %d — txid: %s",
        confirmed_round, txid,
    )

    # --- Decode note from confirmed transaction for verification ------------
    note_decoded = None
    raw_note = txn_result.get("txn", {}).get("txn", {}).get("note")
    if raw_note:
        try:
            note_decoded = json.loads(b64decode(raw_note).decode("utf-8"))
        except (ValueError, KeyError):
            logger.warning("Could not decode note field from confirmed transaction.")

    return AlgorandTxnResult(
        txid            = txid,
        confirmed_round = confirmed_round,
        note_decoded    = note_decoded,
    )


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_payload_from_packaging(packaging_id: str) -> dict:
    """
    Query the Django ORM to assemble the full supply chain payload for a
    given packaging event.

    Traverses all linked models:
        Packaging → Seasoning → MainProcessing → Milk_Productions

    Args:
        packaging_id: UUID primary key of the Packaging record.

    Returns:
        Dictionary ready to be passed to submit_supply_chain_data().

    Note:
        Import Django models here (deferred import) to avoid circular imports
        when this module is used outside the Django application context.
    """
    # Deferred Django ORM imports
    from .models import Packaging  # noqa: PLC0415

    pkg       = Packaging.objects.select_related(
        "seasoning",
        "seasoning__processings__milk_production",
        "operator",
    ).get(id=packaging_id)

    seasoning   = pkg.seasoning
    processing  = seasoning.processings.select_related("milk_production").first()
    milk        = processing.milk_production if processing else None

    payload = {
        "eventTime":        pkg.data_di_confezionamento.isoformat(),
        "packagingId":      str(pkg.id),
        "shelfLife":        pkg.data_di_scadenza.isoformat(),
        "operator":         pkg.operator.username,
        # --- Seasoning phase ---
        "seasoningLot":     seasoning.lotto_id_seasoning,
        "warehouse":        seasoning.magazzino,
        "seasoningStart":   seasoning.data_inizio_stagionatura.isoformat(),
        "seasoningEnd":     seasoning.data_fine_stagionatura.isoformat() if seasoning.data_fine_stagionatura else None,
        "formsTotal":       seasoning.numero_forme,
        "formsBrandedCTF":  seasoning.numero_fontina_marchiate,
        # --- Processing phase ---
        "processingId":     processing.pk if processing else None,
        "productType":      processing.product_type if processing else None,
        "ctfCode":          processing.codice_CTF if processing else None,
        "lotId":            processing.lotto_id if processing else None,
        # --- Milk production phase ---
        "milkCollectionDate": milk.date_process.isoformat() if milk else None,
        "milkTotalLitres":    milk.total_milk if milk else None,
        "farmKind":           milk.farm_kind if milk else None,
        "slot":               milk.slot if milk else None,
    }

    logger.debug("Payload built for packaging %s: %s", packaging_id, payload)
    return payload


# ---------------------------------------------------------------------------
# Django integration helper
# ---------------------------------------------------------------------------

def submit_and_save(packaging_id: str) -> str:
    """
    High-level helper: build payload, submit to Algorand, and persist the
    transaction ID back to the Blockchain_transactions model.

    Args:
        packaging_id: UUID primary key of the Packaging record.

    Returns:
        Algorand transaction ID string.
    """
    from .models import Blockchain_transactions, Packaging  # noqa: PLC0415

    payload = build_payload_from_packaging(packaging_id)
    result  = submit_supply_chain_data(payload)

    pkg = Packaging.objects.get(id=packaging_id)

    Blockchain_transactions.objects.create(
        packaging   = pkg,
        lotto       = payload.get("seasoningLot", ""),
        event_id    = result.txid,
        validation  = True,
    )

    logger.info(
        "Blockchain_transactions record created — txid: %s, lot: %s",
        result.txid, payload.get("seasoningLot"),
    )

    return result.txid


# ---------------------------------------------------------------------------
# CLI / quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Minimal smoke test — submits a dummy payload to Algorand TestNet.

    Usage:
        ALGORAND_MNEMONIC="..." ALGORAND_RECEIVER="..." python algorand_integration.py
    """
    import sys

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    dummy_payload = {
        "eventTime":          "2024-01-15T10:30:00",
        "packagingId":        "test-packaging-001",
        "seasoningLot":       "LOT-2024-001",
        "warehouse":          "Magazzino Aosta",
        "milkTotalLitres":    1211.65,
        "farmKind":           "AL",
        "productType":        "Fontina",
        "formsBrandedCTF":    42,
    }

    try:
        result = submit_supply_chain_data(dummy_payload)
        print(f"\n✓ Transaction confirmed")
        print(f"  txid:            {result.txid}")
        print(f"  confirmed_round: {result.confirmed_round}")
        print(f"  Explorer:        https://testnet.algoexplorer.io/tx/{result.txid}")
    except Exception as exc:
        print(f"\n✗ Error: {exc}")
        sys.exit(1)
