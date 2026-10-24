import logging
from decimal import Decimal
from django.db import transaction

logger = logging.getLogger('accounts')


@transaction.atomic
def merge_users(target_user, source_user):
    """
    Safely merges source_user (e.g. shadow bot user) into target_user (e.g. authenticated web user).
    Combines balances, transfers VPN keys, orders, transactions, referrals, and sets telegram_id.
    Deletes the source_user to eliminate any dual-account desync.
    """
    if not source_user or not target_user or target_user.id == source_user.id:
        return target_user

    logger.info(f"Merging user {source_user.username} (id={source_user.id}) into {target_user.username} (id={target_user.id})")

    # 1. Combine Balances
    target_user.balance = (target_user.balance or Decimal('0.00')) + (source_user.balance or Decimal('0.00'))

    # 2. Synchronize Telegram credentials
    if source_user.telegram_id:
        target_user.telegram_id = str(source_user.telegram_id)
    if source_user.telegram_username:
        target_user.telegram_username = source_user.telegram_username
    if source_user.telegram_bonus_claimed:
        target_user.telegram_bonus_claimed = True

    # 3. Synchronize Google ID
    if source_user.google_id and not target_user.google_id:
        target_user.google_id = source_user.google_id

    # 4. Referral integrity
    if not target_user.referred_by and source_user.referred_by:
        target_user.referred_by = source_user.referred_by

    from apps.accounts.models import CustomUser, DeviceAuthKey, ErrorIncident, MagicLoginToken, TelegramLinkCode
    from apps.vpn.models import VPNKey, UserServerTraffic
    from apps.billing.models import Transaction, PaymentOrder, YooKassaOrder

    CustomUser.objects.filter(referred_by=source_user).update(referred_by=target_user)

    # 5. Transfer all foreign key related models
    Transaction.objects.filter(user=source_user).update(user=target_user)
    PaymentOrder.objects.filter(user=source_user).update(user=target_user)
    YooKassaOrder.objects.filter(user=source_user).update(user=target_user)
    UserServerTraffic.objects.filter(user=source_user).update(user=target_user)
    DeviceAuthKey.objects.filter(user=source_user).update(user=target_user)
    ErrorIncident.objects.filter(user=source_user).update(user=target_user)
    MagicLoginToken.objects.filter(user=source_user).update(user=target_user)
    TelegramLinkCode.objects.filter(user=source_user).update(user=target_user)

    # Transfer used promocodes
    try:
        for promo in source_user.used_promocodes.all():
            target_user.used_promocodes.add(promo)
    except Exception as e:
        logger.warning(f"Error transferring promocodes during merge: {e}")

    # 6. Transfer VPN keys
    VPNKey.objects.filter(user=source_user).update(user=target_user)

    # 7. Unset unique fields on source_user before deleting
    source_user.telegram_id = None
    source_user.telegram_username = None
    source_user.google_id = None
    source_user.save()

    source_user.delete()
    target_user.save()

    # 8. Ensure VPN keys are registered in 3X-UI panel
    from apps.vpn.services import ensure_key_in_panel
    primary_key = target_user.vpn_keys.first()
    if primary_key:
        try:
            ensure_key_in_panel(primary_key)
        except Exception as e:
            logger.warning(f"Failed to sync primary key {primary_key.id} in 3X-UI: {e}")

    return target_user
