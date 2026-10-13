"""
Business dictionary for NexaData AI (PostgreSQL version).
Combine these business meanings with live PostgreSQL schema metadata before
asking the language model to generate SQL.
"""

BUSINESS_DICTIONARY = {
    "product": {
        "description": "Products and catalog information",
        "synonyms": ["item", "goods", "SKU", "merchandise"],
        "tables": {
            "product.product": "Product details, SKU, price, category, reorder level",
            "product.product_category": "Product category or product group",
            "product.supplier": "Supplier/vendor information",
            "product.supplier_product": "Supplier-to-product mapping and supplier cost",
        },
    },
    "master_data": {
        "description": "Reference/master data used by transactions",
        "synonyms": ["customer master", "employee details", "branch", "reference data"],
        "tables": {
            "master.customer": "Customer profile and contact fields",
            "master.employee": "Employee details and branch assignment",
            "master.branch": "Business branch/location",
            "master.payment_method": "Allowed payment methods",
            "master.order_status": "Order status lookup values",
        },
    },
    "transactions": {
        "description": "Orders, payments, inventory movements, returns, and audit records",
        "synonyms": ["sales", "orders", "payments", "transactions", "refunds", "stock movements"],
        "tables": {
            "transactions.sales_order": "Order header: customer, employee, branch, status, date",
            "transactions.sales_order_item": "Products and quantities in each order",
            "transactions.payment": "Payment amount, method, date, and status",
            "transactions.inventory_movement": "Stock IN, OUT, and ADJUSTMENT movements",
            "transactions.product_return": "Returned order items and refund amounts",
            "transactions.transaction_audit": "Audit trail for entity changes",
        },
    },
}

BUSINESS_TERMS = {
    "revenue": {
        "meaning": "Successful payments received",
        "preferred_table": "transactions.payment",
        "preferred_column": "amount",
        "calculation": "SUM(amount)",
        "caution": "Filter payment_status = 'Success' when asked for successful payments. Recognized revenue may follow different accounting rules.",
    },
    "total sales": {
        "meaning": "Order line value before returns",
        "preferred_table": "transactions.sales_order_item",
        "calculation": "SUM(quantity * unit_price - discount_amount)",
    },
    "customer count": {
        "meaning": "Number of customer records",
        "preferred_table": "master.customer",
        "calculation": "COUNT(DISTINCT customer_id)",
    },
    "refunds": {
        "meaning": "Amounts refunded for product returns",
        "preferred_table": "transactions.product_return",
        "preferred_column": "refund_amount",
        "calculation": "SUM(refund_amount)",
    },
    "inventory": {
        "meaning": "Inventory movements; current stock requires netting IN and OUT movements",
        "preferred_table": "transactions.inventory_movement",
        "caution": "Do not assume movements are complete unless the source data guarantees it.",
    },
}

JOIN_RELATIONSHIPS = [
    "product.product.category_id = product.product_category.category_id",
    "product.supplier_product.product_id = product.product.product_id",
    "product.supplier_product.supplier_id = product.supplier.supplier_id",
    "master.employee.branch_id = master.branch.branch_id",
    "transactions.sales_order.customer_id = master.customer.customer_id",
    "transactions.sales_order.employee_id = master.employee.employee_id",
    "transactions.sales_order.branch_id = master.branch.branch_id",
    "transactions.sales_order.order_status_id = master.order_status.order_status_id",
    "transactions.sales_order_item.order_id = transactions.sales_order.order_id",
    "transactions.sales_order_item.product_id = product.product.product_id",
    "transactions.payment.order_id = transactions.sales_order.order_id",
    "transactions.payment.payment_method_id = master.payment_method.payment_method_id",
    "transactions.inventory_movement.product_id = product.product.product_id",
    "transactions.inventory_movement.branch_id = master.branch.branch_id",
    "transactions.product_return.order_item_id = transactions.sales_order_item.order_item_id",
]
