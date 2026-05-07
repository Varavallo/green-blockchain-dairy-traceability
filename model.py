"""
models.py — Fontina PDO Traceability Platform
==============================================
Django data model for the Fontina PDO cheese supply chain traceability platform.
Each model corresponds to a phase of the production chain:

    Milk_Productions → MainProcessing → Seasoning → Classifica → Packaging → Blockchain_transactions

Auxiliary models: MilkImages, SubProcessing, Milk_analysis

Reference:
    Varavallo et al. (2022). Traceability Platform Based on Green Blockchain:
    An Application Case Study in Dairy Supply Chain.
    Sustainability, 14(6), 3321. https://doi.org/10.3390/su14063321

Authors: Giuseppe Varavallo, Giuseppe Caragnano, Fabrizio Bertone,
         Luca Vernetti-Prot, Olivier Terzo — LINKS Foundation / IAR Aosta
"""

import uuid
import json

from django.contrib.auth.models import User
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone


# ==============================================================================
# PHASE 1 — MILK PRODUCTION
# Transporter collects raw milk from farmers and registers delivery data.
# ==============================================================================

class Milk_Productions(models.Model):
    """
    Records each milk collection run performed by the transporter.

    A single run aggregates milk from multiple farmers. The transporter logs
    total volume, farm type, collection date, and time slot. Individual
    farmer receipts are attached via MilkImages.
    """

    FARM_KIND_CHOICES = [
        ('FV', 'Fondo Valle'),
        ('AL', 'Alpeggio'),
    ]
    SLOT_CHOICES = [
        ('Mattina', 'Mattina'),
        ('Sera',    'Sera'),
    ]

    operator       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='milk_productions')
    total_milk     = models.FloatField(verbose_name="Total milk quantity (L)")
    farm_kind      = models.CharField(max_length=50, choices=FARM_KIND_CHOICES, null=True, blank=True)
    date_process   = models.DateField(verbose_name="Collection date")
    slot           = models.CharField(max_length=50, choices=SLOT_CHOICES, null=True, blank=True)
    created        = models.DateTimeField(auto_now_add=True)
    updated        = models.DateTimeField(auto_now=True)

    def __str__(self):
        return '{} {} | {}L | {}'.format(
            self.date_process.strftime('%d-%m-%Y'),
            self.slot,
            self.total_milk,
            self.operator,
        )

    class Meta:
        verbose_name        = 'Milk Production'
        verbose_name_plural = 'Milk Productions'
        ordering            = ['-date_process']


class MilkImages(models.Model):
    """
    Stores receipt images (photos or scans) produced by the existing milk
    collection system for each farmer delivery within a production run.
    """

    milk_production = models.ForeignKey(
        Milk_Productions,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='milk_receipts/', null=True, blank=True)

    def __str__(self):
        return 'Receipt — {}'.format(self.milk_production)

    class Meta:
        verbose_name        = 'Milk Receipt Image'
        verbose_name_plural = 'Milk Receipt Images'
        ordering            = ['-pk']


class Milk_analysis(models.Model):
    """
    Records laboratory analysis results for a milk production batch.

    Parameters tracked: fat, protein, lactose, casein content,
    somatic cell count, and CBS score.
    """

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operator          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='milk_analyses')
    milk_production   = models.ForeignKey(Milk_Productions, on_delete=models.CASCADE, related_name='analyses')
    grasso            = models.FloatField(verbose_name='Fat (%)')
    proteine          = models.FloatField(verbose_name='Protein (%)')
    lattosio          = models.FloatField(verbose_name='Lactose (%)')
    caseine           = models.FloatField(verbose_name='Casein (%)')
    cellule_som       = models.FloatField(verbose_name='Somatic cell count')
    cbs_latte         = models.FloatField(verbose_name='CBS score')
    details           = models.TextField(null=True, blank=True)
    created           = models.DateTimeField(auto_now_add=True)
    updated           = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Analysis — {}'.format(self.milk_production)

    class Meta:
        verbose_name        = 'Milk Analysis'
        verbose_name_plural = 'Milk Analyses'
        ordering            = ['-created']


# ==============================================================================
# PHASE 2 — PROCESSING
# Dairy operator transforms raw milk into semi-finished cheese ("white form").
# ==============================================================================

class Seasoning(models.Model):
    """
    Represents a seasoning lot — a group of semi-finished cheese forms
    transferred to a maturation warehouse after processing.

    Declared here (before MainProcessing) because MainProcessing holds
    a ForeignKey to Seasoning.
    """

    operator                   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seasonings')
    main_process_id            = models.CharField(max_length=60, null=True, blank=True)
    lotto_id_seasoning         = models.CharField(max_length=60, null=True, blank=True, verbose_name='Lot ID')
    peso_totale                = models.FloatField(null=True, blank=True, verbose_name='Total weight (kg)')
    numero_bolla_consegna      = models.CharField(max_length=60, null=True, blank=True, verbose_name='Delivery note number')
    data_inizio_stagionatura   = models.DateField(verbose_name='Seasoning start date')
    data_fine_stagionatura     = models.DateTimeField(null=True, blank=True, verbose_name='Seasoning end date')
    numero_fontina_marchiate   = models.PositiveIntegerField(null=True, blank=True, verbose_name='CTF-branded forms')
    numero_forme               = models.PositiveIntegerField(null=True, blank=True, verbose_name='Total forms')
    magazzino                  = models.CharField(max_length=60, null=True, blank=True, verbose_name='Warehouse')
    details                    = models.TextField(null=True, blank=True)
    created                    = models.DateTimeField(auto_now_add=True)
    updated                    = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Lot {} | {} | {} | {}'.format(
            self.lotto_id_seasoning,
            self.data_inizio_stagionatura.strftime('%d-%m-%Y'),
            self.magazzino,
            self.operator,
        )

    class Meta:
        verbose_name        = 'Seasoning'
        verbose_name_plural = 'Seasonings'
        ordering            = ['-created']


class MainProcessing(models.Model):
    """
    Records the transformation of a milk production batch into semi-finished
    cheese forms at the dairy.

    Links a Milk_Productions record to a Seasoning lot and tracks product
    type, number of forms, casein numbering, and CTF consortium code.
    """

    PROCESS_TIME_CHOICES = [
        ('M', 'Mattina'),
        ('S', 'Sera'),
    ]
    CHEESE_KIND_CHOICES = [
        ('Fontina',          'Fontina'),
        ('Toma di Gressoney', 'Toma di Gressoney'),
    ]

    operator           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='processings')
    milk_production    = models.ForeignKey(Milk_Productions, on_delete=models.CASCADE, related_name='processings')
    seasoning          = models.ForeignKey(Seasoning, on_delete=models.PROTECT, null=True, related_name='processings')
    product_type       = models.CharField(max_length=50, choices=CHEESE_KIND_CHOICES, null=True, blank=True)
    peso_medio         = models.FloatField(null=True, blank=True, verbose_name='Average form weight (kg)')
    peso_totale        = models.FloatField(verbose_name='Total weight (kg)')
    codice_CTF         = models.IntegerField(null=True, blank=True, verbose_name='CTF code')
    lotto_id           = models.CharField(max_length=20, null=True, blank=True, verbose_name='Lot ID')
    nr_forme_totali    = models.IntegerField(null=True, blank=True, verbose_name='Total forms produced')
    start_nr_caseina   = models.CharField(max_length=20, null=True, blank=True, verbose_name='Casein number (start)')
    end_nr_caseina     = models.CharField(max_length=20, null=True, blank=True, verbose_name='Casein number (end)')
    details            = models.TextField(null=True, blank=True)
    date_process       = models.DateTimeField(default=timezone.now, null=True, blank=True)
    process_time       = models.CharField(max_length=50, choices=PROCESS_TIME_CHOICES, null=True, blank=True)
    created            = models.DateTimeField(auto_now_add=True)
    updated            = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Processing {} | {} {} | Forms: {} | {}'.format(
            self.pk,
            self.milk_production.date_process.strftime('%d-%m-%Y'),
            self.milk_production.slot,
            self.nr_forme_totali,
            self.operator,
        )

    class Meta:
        verbose_name        = 'Processing'
        verbose_name_plural = 'Processings'


class SubProcessing(models.Model):
    """
    Records per-vat (caldaia) details within a single processing session.

    A MainProcessing event may involve multiple vats; each vat's milk
    quantity, forms produced, and casein numbering are tracked here.
    """

    processing       = models.ForeignKey(MainProcessing, on_delete=models.PROTECT, related_name='sub_processings')
    caldaia_id       = models.CharField(max_length=50, verbose_name='Vat ID')
    quantita_latte   = models.CharField(max_length=50, null=True, blank=True, verbose_name='Milk quantity (L)')
    nr_forme_prodotte = models.CharField(max_length=50, verbose_name='Forms produced')
    start_nr_caseina = models.CharField(max_length=20, verbose_name='Casein number (start)')
    end_nr_caseina   = models.CharField(max_length=20, verbose_name='Casein number (end)')
    created          = models.DateTimeField(auto_now_add=True)
    updated          = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'SubProcessing {} — Vat {}'.format(self.processing, self.caldaia_id)

    class Meta:
        verbose_name        = 'Sub-Processing'
        verbose_name_plural = 'Sub-Processings'


# ==============================================================================
# PHASE 3 — SEASONING  (model declared above, before MainProcessing)
# Semi-finished forms mature in a temperature/humidity-controlled warehouse
# for a minimum of 3 months before CTF quality inspection.
# ==============================================================================

# ==============================================================================
# PHASE 3b — CTF QUALITY AUDIT (Classifica)
# Fontina Protection Consortium experts inspect and brand eligible forms.
# ==============================================================================

class Classifica(models.Model):
    """
    Records the CTF quality audit for one or more seasoning lots.

    Experts from the Fontina Protection Consortium evaluate each form:
    those passing quality criteria are branded with the CTF logo;
    those failing are downgraded (declassate) and cannot be sold as Fontina PDO.
    """

    operator                  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='classifiche')
    data_classifica           = models.DateField(null=True, verbose_name='Audit date')
    numero_verbale            = models.CharField(max_length=60, null=True, blank=True, verbose_name='Report number')
    lotti                     = models.ManyToManyField(Seasoning, blank=True, related_name='classifiche')
    numero_forme_valutate     = models.PositiveIntegerField(null=True, blank=True, verbose_name='Forms evaluated')
    numero_forme_marchiate    = models.PositiveIntegerField(null=True, blank=True, verbose_name='Forms branded (CTF)')
    numero_forme_declassate   = models.PositiveIntegerField(null=True, blank=True, verbose_name='Forms downgraded')
    peso_fontina              = models.FloatField(null=True, blank=True, verbose_name='Weight — Fontina PDO (kg)')
    peso_formaggio            = models.FloatField(null=True, blank=True, verbose_name='Weight — downgraded (kg)')
    magazzino                 = models.CharField(max_length=60, null=True, blank=True, verbose_name='Warehouse')
    details                   = models.TextField(null=True, blank=True)
    created                   = models.DateTimeField(auto_now_add=True)
    updated                   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Audit {} | {} | {} | {} branded'.format(
            self.pk,
            self.data_classifica.strftime('%d-%m-%Y') if self.data_classifica else '—',
            self.magazzino,
            self.numero_forme_marchiate,
        )

    class Meta:
        verbose_name        = 'CTF Quality Audit'
        verbose_name_plural = 'CTF Quality Audits'
        ordering            = ['-created']


# ==============================================================================
# PHASE 4 — PACKAGING
# Branded forms are portioned and packaged. At this stage all supply chain
# data is aggregated and submitted to the Algorand blockchain as a single
# JSON transaction, generating a QR Code for the consumer.
# ==============================================================================

class Packaging(models.Model):
    """
    Records the packaging event for a seasoning lot.

    This is the blockchain trigger point: once the operator submits this
    record, the system queries all linked supply chain phases and sends
    the aggregated JSON payload to the Algorand blockchain.
    A QR Code is then generated linking to the transaction on Algo Explorer.
    """

    id                        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seasoning                 = models.ForeignKey(Seasoning, on_delete=models.CASCADE, related_name='packagings')
    operator                  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='packagings')
    data_di_confezionamento   = models.DateTimeField(default=timezone.now, verbose_name='Packaging date')
    data_di_scadenza          = models.DateTimeField(verbose_name='Expiry date')
    created                   = models.DateTimeField(auto_now_add=True)
    updated                   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Packaging {} | {} | {}'.format(
            self.pk,
            self.seasoning,
            self.operator,
        )

    class Meta:
        verbose_name        = 'Packaging'
        verbose_name_plural = 'Packagings'
        ordering            = ['-created']


# ==============================================================================
# PHASE 5 — BLOCKCHAIN TRANSACTION
# Algorand transaction record linking a packaging event to an on-chain txn.
# ==============================================================================

class Blockchain_transactions(models.Model):
    """
    Stores the Algorand blockchain transaction associated with a packaging event.

    The `event_id` field holds the Algorand transaction ID, which can be
    verified on Algo Explorer. `validation` is set to True once the transaction
    is confirmed on-chain (typically within a few seconds via PPoS consensus).

    Transaction cost: ~0.001 ALGO (< $0.01 USD). One transaction per lot.
    """

    packaging   = models.ForeignKey(Packaging, on_delete=models.PROTECT, related_name='blockchain_txns')
    validation  = models.BooleanField(default=False, verbose_name='Confirmed on-chain')
    lotto       = models.CharField(max_length=50, verbose_name='Lot reference')
    event_id    = models.CharField(max_length=60, null=True, blank=True, verbose_name='Algorand transaction ID')
    created     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return 'Txn {} | Lot {} | Confirmed: {}'.format(
            self.event_id or '—',
            self.lotto,
            self.validation,
        )

    class Meta:
        verbose_name        = 'Blockchain Transaction'
        verbose_name_plural = 'Blockchain Transactions'
        ordering            = ['-created']


# ==============================================================================
# UTILITY
# ==============================================================================

def validate_quantity(request, txn_id: int, quantity: float) -> JsonResponse:
    """
    Validates that a quantity entered during processing does not exceed
    the total milk available in the linked production record.

    Used as an AJAX endpoint during the processing form submission.

    Args:
        request:  Django HTTP request.
        txn_id:   Primary key of the Milk_Productions record.
        quantity: Quantity (in litres) entered by the operator.

    Returns:
        JsonResponse with {'valid': True} if quantity <= total_milk, else False.
    """
    production = get_object_or_404(Milk_Productions, id=txn_id)
    return JsonResponse({'valid': float(quantity) <= production.total_milk})
