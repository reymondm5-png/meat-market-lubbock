import datetime as dt
import unittest
from collector import classify, price_per_lb, food_king_candidates, united_candidates, run

TODAY = dt.date(2026, 11, 2)
FOOD = '''<html><body><header>28 Oct- Nov 3</header><table><tr><th>Product</th><th>Brand</th><th>Price</th><th>Unit</th><th>Category</th></tr>
<tr><td>PORK SIRLOIN CHOPS</td><td></td><td>99¢/LB</td><td>LB</td><td>MEAT</td></tr>
<tr><td>FULLY COOKED BREADED CHICKEN BREAST CHUNKS</td><td></td><td>99¢/LB</td><td>LB</td><td>MEAT</td></tr>
<tr><td>BONELESS SKINLESS CHICKEN BREAST</td><td></td><td>$1.99/LB</td><td>LB</td><td>MEAT</td></tr>
<tr><td>BONELESS CHUCK ROAST</td><td></td><td>$389/LB</td><td>LB</td><td>MEAT</td></tr>
<tr><td>GROUND BEEF 80/20</td><td></td><td>$5.00/EA</td><td>EA</td><td>MEAT</td></tr></table></body></html>'''
UNITED = '''<html><body><h1>United Supermarkets Weekly Ad</h1><p>Oct 28, 2026 to Nov 3, 2026</p>
<section><h3>Bone-In Center Cut Pork Chops</h3><p>Nov 3, 2026$3.97</p></section>
<section><h3>Ground Beef Value Pack</h3><p>Nov 3, 2026$5.97</p></section>
</body></html>'''

class TestCollector(unittest.TestCase):
    def test_price_units(self):
        self.assertEqual(price_per_lb('$389/LB'), 3.89)
        self.assertEqual(price_per_lb('99¢/LB'), .99)
        self.assertEqual(price_per_lb('$3.96/LB'), 3.96)
        self.assertIsNone(price_per_lb('$8.96/EA'))
        self.assertIsNone(price_per_lb('3.97'))

    def test_classification_excludes_different_product(self):
        self.assertIsNone(classify('Fully cooked breaded spicy chicken breast chunks'))
        self.assertIsNone(classify('Turkey burger patties'))
        self.assertIsNone(classify('Bone-in chuck roast'))
        self.assertEqual(classify('Boneless chuck roast'), 'Boneless chuck roast')

    def test_food_king_recommended_not_autopublished(self):
        rows, status = food_king_candidates(FOOD, TODAY)
        self.assertEqual({r['meat'] for r in rows}, {'Pork chops', 'Chicken breast', 'Boneless chuck roast'})
        self.assertEqual(next(r for r in rows if r['meat']=='Pork chops')['pricePerLb'], .99)
        self.assertFalse(next(r for r in rows if r['meat']=='Pork chops')['priceIncludesMarkup'])
        self.assertEqual(food_king_candidates(FOOD, dt.date(2026,11,9))[0], [])

    def test_united_requires_price_review(self):
        rows, status = united_candidates(UNITED, 'https://www.weeklyads.now/united-supermarkets/test', TODAY)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('pricePerLb' not in r for r in rows))

    def test_pipeline_never_publishes_unverified(self):
        def fixture_get(url):
            if 'foodking' in url: return FOOD
            if url.endswith('united-supermarkets'): return '<a href="/united-supermarkets/united-supermarkets-flyer-test">current</a>'
            return UNITED
        feed = run(TODAY, fixture_get)
        self.assertEqual(feed['prices'], [])
        self.assertEqual(len(feed['candidates']), 5)

if __name__ == '__main__': unittest.main()
