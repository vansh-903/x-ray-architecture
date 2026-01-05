"""
Demo: Competitor Selection Pipeline with X-Ray Instrumentation

This example simulates a competitor product selection system:
1. Generate keywords from product title
2. Search for candidate products
3. Filter by price, rating, category
4. Select the best match

Run this demo:
    # First, start the API server:
    cd api && uvicorn main:app --reload

    # Then run the demo:
    python -m examples.demo
"""

import random
import sys
from dataclasses import dataclass
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, str(__file__).rsplit("examples", 1)[0])

from sdk import XRay


# --- Simulated Data ---

@dataclass
class Product:
    id: str
    title: str
    category: str
    price: float
    rating: float


def generate_mock_products(count: int, include_bad_matches: bool = True) -> List[Product]:
    """Generate mock product data for the demo."""
    products = []

    # Good matches (phone cases)
    for i in range(count // 2):
        products.append(Product(
            id=f"case_{i}",
            title=f"Phone Case Model {i}",
            category="phone_accessories",
            price=random.uniform(10, 50),
            rating=random.uniform(3.5, 5.0)
        ))

    # Bad matches (laptop stands) - simulating the bug
    if include_bad_matches:
        for i in range(count // 4):
            products.append(Product(
                id=f"stand_{i}",
                title=f"Laptop Stand Model {i}",
                category="computer_accessories",
                price=random.uniform(30, 100),
                rating=random.uniform(4.0, 5.0)
            ))

    # Other products (will be filtered out)
    for i in range(count // 4):
        products.append(Product(
            id=f"other_{i}",
            title=f"Random Product {i}",
            category="other",
            price=random.uniform(5, 200),
            rating=random.uniform(1.0, 5.0)
        ))

    random.shuffle(products)
    return products


# --- Pipeline Steps ---

def generate_keywords(title: str) -> List[str]:
    """
    Simulate LLM keyword generation.
    This is where the bug happens - it generates 'stand' as a keyword.
    """
    keywords = []

    # Extract words from title
    words = title.lower().split()
    keywords.extend([w for w in words if len(w) > 3])

    # Bug: LLM also generates related but wrong keywords
    if "case" in title.lower():
        keywords.extend(["case", "cover", "protection"])
        # BUG: Also adds 'stand' due to word association
        keywords.append("stand")

    return list(set(keywords))


def search_products(keywords: List[str], all_products: List[Product]) -> List[Product]:
    """Search for products matching keywords."""
    results = []
    for product in all_products:
        title_lower = product.title.lower()
        if any(kw in title_lower for kw in keywords):
            results.append(product)
    return results


def filter_products(
    products: List[Product],
    step,  # X-Ray step for tracking
    max_price: float = 100,
    min_rating: float = 3.0,
    target_category: str = "phone_accessories"
) -> List[Product]:
    """Filter products and track rejections."""
    filtered = []

    for product in products:
        # Price filter
        if product.price > max_price:
            step.reject(product.id, "price_too_high", {
                "price": product.price,
                "threshold": max_price
            })
            continue

        # Rating filter
        if product.rating < min_rating:
            step.reject(product.id, "low_rating", {
                "rating": product.rating,
                "threshold": min_rating
            })
            continue

        # Category filter (this should catch laptop stands, but doesn't always)
        if product.category != target_category:
            # Bug: Sometimes the category filter is too lenient
            if random.random() < 0.3:  # 30% chance of false negative
                step.reject(product.id, "category_mismatch", {
                    "category": product.category,
                    "expected": target_category
                })
                continue

        # Product passed all filters
        step.accept(product.id, "passed_all_filters", {
            "price": product.price,
            "rating": product.rating,
            "category": product.category
        })
        filtered.append(product)

    return filtered


def select_best(products: List[Product], step) -> Product:
    """Select the best matching product."""
    if not products:
        raise ValueError("No products to select from")

    # Score products (higher is better)
    scored = []
    for product in products:
        score = (product.rating / 5.0) * 0.6 + (1 - product.price / 100) * 0.4
        scored.append((product, score))

    # Sort by score
    scored.sort(key=lambda x: x[1], reverse=True)

    best_product, best_score = scored[0]

    # Record the decision
    step.decide(
        decision="select_best_competitor",
        selected=best_product.id,
        reason="highest_combined_score",
        score=best_score,
        alternatives=[{
            "id": p.id,
            "score": s,
            "title": p.title
        } for p, s in scored[1:5]]  # Top 5 alternatives
    )

    return best_product


# --- Main Pipeline ---

def run_competitor_selection(product_title: str, xray: XRay):
    """
    Run the competitor selection pipeline with X-Ray instrumentation.
    """
    # Generate mock product catalog
    all_products = generate_mock_products(500)

    with xray.run(input={"product_title": product_title}) as run:

        # Step 1: Generate keywords
        with run.step("generate_keywords", step_type="generate") as step:
            step.set_input({"title": product_title})
            keywords = generate_keywords(product_title)
            step.set_output({"keywords": keywords})
            print(f"Step 1: Generated keywords: {keywords}")

        # Step 2: Search products
        with run.step("search_products", step_type="transform") as step:
            step.set_input({"keywords": keywords})
            candidates = search_products(keywords, all_products)
            step.set_output({"count": len(candidates)})
            step.set_input_count(len(all_products))
            step.set_output_count(len(candidates))
            print(f"Step 2: Found {len(candidates)} candidates")

        # Step 3: Filter products
        with run.step("filter_candidates", step_type="filter") as step:
            step.set_input_count(len(candidates))
            filtered = filter_products(candidates, step)
            step.set_output_count(len(filtered))
            print(f"Step 3: {len(filtered)} products passed filters")

        # Step 4: Select best
        with run.step("select_best", step_type="select") as step:
            if filtered:
                best = select_best(filtered, step)
                run.set_output({
                    "selected_id": best.id,
                    "selected_title": best.title,
                    "selected_category": best.category
                })
                print(f"Step 4: Selected: {best.title} ({best.category})")

                # Check if we got a bad match
                if best.category != "phone_accessories":
                    print(f"\n⚠️  BAD MATCH DETECTED!")
                    print(f"   Input: {product_title}")
                    print(f"   Output: {best.title} (category: {best.category})")
                    print(f"   This is the kind of bug X-Ray helps you debug!")
            else:
                run.set_output({"error": "No matching products found"})
                print("Step 4: No products to select from")

    print(f"\nRun completed: {run.run_id}")
    return run.run_id


# --- Run Demo ---

if __name__ == "__main__":
    print("=" * 60)
    print("X-Ray Demo: Competitor Selection Pipeline")
    print("=" * 60)

    # Initialize X-Ray
    xray = XRay(
        pipeline="competitor_selection",
        api_url="http://localhost:8000",
        offline_mode="buffer"  # Save locally if API is down
    )

    # Run the pipeline
    print("\nRunning pipeline for: 'iPhone 15 Case - Premium Protection'\n")

    run_id = run_competitor_selection(
        product_title="iPhone 15 Case - Premium Protection",
        xray=xray
    )

    print("\n" + "=" * 60)
    print("To debug this run:")
    print(f"  GET http://localhost:8000/runs/{run_id}")
    print("\nTo find all filter steps with high rejection rates:")
    print("  GET http://localhost:8000/steps?step_type=filter&rejection_rate_gt=0.5")
    print("=" * 60)
