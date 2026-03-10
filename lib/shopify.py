"""Shopify operations via external-tool CLI."""

import logging

from .connectors import call_tool, SHOPIFY_SOURCE_ID

logger = logging.getLogger(__name__)


async def search_orders(query: str, max_results: int = 5) -> list[dict]:
    """Search Shopify orders."""
    try:
        result = await call_tool(SHOPIFY_SOURCE_ID, "shopify_developer_app-search-orders", {
            "query": query,
            "max": max_results,
        })
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.error(f"Shopify order search failed: {e}")
        return []


async def get_order(order_id: str) -> dict | None:
    """Get full order details by Shopify order ID (gid://shopify/Order/...)."""
    try:
        result = await call_tool(SHOPIFY_SOURCE_ID, "shopify_developer_app-get-order", {
            "orderId": order_id,
        })
        if isinstance(result, dict):
            return result.get("order", result)
        return result
    except Exception as e:
        logger.error(f"Shopify get order failed: {e}")
        return None


async def search_customers(query: str) -> list[dict]:
    """Search Shopify customers."""
    try:
        result = await call_tool(SHOPIFY_SOURCE_ID, "shopify_developer_app-search-customers", {
            "query": query,
        })
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.error(f"Shopify customer search failed: {e}")
        return []


async def lookup_customer_orders(email: str) -> list[dict]:
    """Look up a customer by email and get their order details."""
    customers = await search_customers(f"email:{email}")
    if not customers:
        return []

    customer = customers[0]
    order_nodes = []
    orders_data = customer.get("orders", {})
    if isinstance(orders_data, dict):
        order_nodes = orders_data.get("nodes", [])

    detailed_orders = []
    for order_node in order_nodes[:5]:
        order_id = order_node.get("id")
        if order_id:
            detail = await get_order(order_id)
            if detail:
                detailed_orders.append(detail)

    return detailed_orders


def extract_order_summary(order: dict) -> dict:
    """Extract key fields from an order for display/prompt context."""
    name = order.get("name", "")
    status = order.get("displayFulfillmentStatus", "")
    financial = order.get("displayFinancialStatus", "")

    # Customer info
    customer = order.get("customer", {}) or {}
    customer_name = customer.get("displayName", "")
    customer_email = customer.get("email", "")

    # Line items
    items = []
    line_items = order.get("lineItems", {})
    edges = line_items.get("edges", []) if isinstance(line_items, dict) else []
    for edge in edges:
        node = edge.get("node", {})
        items.append({
            "title": node.get("title", ""),
            "variant": node.get("variantTitle", ""),
            "quantity": node.get("quantity", 1),
            "fulfillment_status": node.get("fulfillmentStatus", ""),
        })

    # Fulfillment info
    fulfillments = []
    for f in order.get("fulfillments", []):
        fulfillments.append({
            "status": f.get("status", ""),
            "display_status": f.get("displayStatus", ""),
            "estimated_delivery": f.get("estimatedDeliveryAt"),
            "in_transit_at": f.get("inTransitAt"),
            "delivered_at": f.get("deliveredAt"),
        })

    # Shipping line
    shipping_line = order.get("shippingLine", {}) or {}
    carrier = shipping_line.get("source", "")
    service = shipping_line.get("title", "")

    # Metafields (prescription/ring data)
    metafields = {}
    meta_nodes = order.get("metafields", {})
    if isinstance(meta_nodes, dict):
        for node in meta_nodes.get("nodes", []):
            key = node.get("key", "")
            ns = node.get("namespace", "")
            if ns == "halo_prescription":
                metafields[key] = node.get("value", "")

    return {
        "order_number": name,
        "order_id": order.get("id", ""),
        "fulfillment_status": status,
        "financial_status": financial,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "items": items,
        "fulfillments": fulfillments,
        "carrier": carrier,
        "shipping_service": service,
        "metafields": metafields,
        "cancelled_at": order.get("cancelledAt"),
        "cancel_reason": order.get("cancelReason"),
    }
