"""
Test script for X-Ray SDK and API.

Tests:
1. Scale test: 1000+ runs
2. Failure cases: API errors, exceptions in pipeline
3. Query performance
"""

import random
import sys
import time
from dataclasses import dataclass
from typing import List

sys.path.insert(0, str(__file__).rsplit("tests", 1)[0])

from sdk import XRay


@dataclass
class Product:
    id: str
    title: str
    category: str
    price: float
    rating: float


def generate_products(count: int) -> List[Product]:
    """Generate mock products."""
    products = []
    categories = ["phone_accessories", "computer_accessories", "audio", "gaming"]

    for i in range(count):
        products.append(Product(
            id=f"product_{i}",
            title=f"Product {i}",
            category=random.choice(categories),
            price=random.uniform(5, 200),
            rating=random.uniform(1, 5)
        ))
    return products


def run_pipeline(xray: XRay, run_number: int, should_fail: bool = False):
    """Run a single pipeline execution."""
    products = generate_products(100)

    try:
        with xray.run(input={"run_number": run_number, "product_count": len(products)}) as run:

            # Step 1: Generate (always succeeds)
            with run.step("generate_keywords", step_type="generate") as step:
                step.set_input({"query": f"test query {run_number}"})
                keywords = ["keyword1", "keyword2", "keyword3"]
                step.set_output({"keywords": keywords})

            # Step 2: Filter
            with run.step("filter_products", step_type="filter") as step:
                step.set_input_count(len(products))

                filtered = []
                for product in products:
                    if product.price > 150:
                        step.reject(product.id, "price_too_high", {"price": product.price})
                    elif product.rating < 2:
                        step.reject(product.id, "low_rating", {"rating": product.rating})
                    elif product.category not in ["phone_accessories", "computer_accessories"]:
                        step.reject(product.id, "wrong_category", {"category": product.category})
                    else:
                        step.accept(product.id)
                        filtered.append(product)

                step.set_output_count(len(filtered))

            # Step 3: Select (simulate failure if requested)
            if should_fail:
                raise ValueError("Simulated pipeline failure!")

            with run.step("select_best", step_type="select") as step:
                if filtered:
                    best = max(filtered, key=lambda p: p.rating)
                    step.decide(
                        decision="select_best",
                        selected=best.id,
                        reason="highest_rating",
                        score=best.rating
                    )
                    run.set_output({"selected": best.id, "rating": best.rating})
                else:
                    run.set_output({"error": "no_products_found"})

    except Exception as e:
        # Pipeline failed - run context manager handles status
        pass

    return run.run_id


def test_scale(num_runs: int = 1000):
    """Test with many runs."""
    print(f"\n{'='*60}")
    print(f"SCALE TEST: {num_runs} runs")
    print(f"{'='*60}\n")

    xray = XRay(
        pipeline="scale_test",
        api_url="http://localhost:8000",
        offline_mode="buffer"
    )

    start_time = time.time()
    run_ids = []

    for i in range(num_runs):
        run_id = run_pipeline(xray, i)
        run_ids.append(run_id)

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            print(f"  Completed {i + 1}/{num_runs} runs ({rate:.1f} runs/sec)")

    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.2f}s ({num_runs / elapsed:.1f} runs/sec)")

    return run_ids


def test_failures(num_failures: int = 50):
    """Test failure cases."""
    print(f"\n{'='*60}")
    print(f"FAILURE TEST: {num_failures} failing runs")
    print(f"{'='*60}\n")

    xray = XRay(
        pipeline="failure_test",
        api_url="http://localhost:8000",
        offline_mode="buffer"
    )

    for i in range(num_failures):
        run_pipeline(xray, i, should_fail=True)

    print(f"  Created {num_failures} failed runs")


def test_queries():
    """Test API queries."""
    print(f"\n{'='*60}")
    print("QUERY TEST")
    print(f"{'='*60}\n")

    import requests

    base_url = "http://localhost:8000"

    # Test 1: List all runs
    print("1. GET /runs (first 10)")
    resp = requests.get(f"{base_url}/runs?limit=10")
    data = resp.json()
    print(f"   Total runs: {data['total']}")
    print(f"   First 10: {[r['run_id'][:15] + '...' for r in data['runs'][:5]]}")

    # Test 2: Filter by pipeline
    print("\n2. GET /runs?pipeline=scale_test")
    resp = requests.get(f"{base_url}/runs?pipeline=scale_test&limit=5")
    data = resp.json()
    print(f"   Scale test runs: {data['total']}")

    # Test 3: Filter by status (failed)
    print("\n3. GET /runs?status=failed")
    resp = requests.get(f"{base_url}/runs?status=failed")
    data = resp.json()
    print(f"   Failed runs: {data['total']}")

    # Test 4: Query filter steps with high rejection rate
    print("\n4. GET /steps?step_type=filter&rejection_rate_gt=0.5")
    resp = requests.get(f"{base_url}/steps?step_type=filter&rejection_rate_gt=0.5&limit=5")
    data = resp.json()
    print(f"   Filter steps with >50% rejection: {data['total']}")
    for step in data['steps'][:3]:
        print(f"   - {step['step_name']}: rejection_rate={step['rejection_rate']:.2%}")

    # Test 5: Get a single run detail
    print("\n5. GET /runs/{id} (single run detail)")
    resp = requests.get(f"{base_url}/runs?limit=1")
    if resp.json()['runs']:
        run_id = resp.json()['runs'][0]['run_id']
        resp = requests.get(f"{base_url}/runs/{run_id}")
        run = resp.json()
        print(f"   Run: {run['run_id']}")
        print(f"   Pipeline: {run['pipeline']}")
        print(f"   Status: {run['status']}")
        print(f"   Steps: {len(run['steps'])}")
        for step in run['steps']:
            rej_rate = step.get('rejection_rate')
            rej_str = f"{rej_rate:.1%}" if rej_rate else "N/A"
            print(f"     - {step['name']} ({step['step_type']}): rejection={rej_str}")


def test_offline_mode():
    """Test offline buffering."""
    print(f"\n{'='*60}")
    print("OFFLINE MODE TEST")
    print(f"{'='*60}\n")

    # Use wrong URL to simulate API being down
    xray = XRay(
        pipeline="offline_test",
        api_url="http://localhost:9999",  # Wrong port
        offline_mode="buffer"
    )

    print("  Running pipeline with API unavailable...")
    run_id = run_pipeline(xray, 999)
    print(f"  Run completed: {run_id}")
    print(f"  Data buffered to: ~/.xray/offline/")

    # Check buffer
    from pathlib import Path
    offline_dir = Path.home() / ".xray" / "offline"
    if offline_dir.exists():
        files = list(offline_dir.glob("*.json"))
        print(f"  Buffered files: {len(files)}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("X-RAY SDK & API TEST SUITE")
    print("="*60)

    # Run scale test
    test_scale(1000)

    # Run failure test
    test_failures(50)

    # Run query tests
    test_queries()

    # Test offline mode
    test_offline_mode()

    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60 + "\n")
