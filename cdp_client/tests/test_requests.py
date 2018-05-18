from cdp_client import cdp
import unittest


class RequestsTester(unittest.TestCase):
    def __init__(self, method_name):
        unittest.TestCase.__init__(self, method_name)
        self._requests = None

    def setUp(self):
        self._requests = cdp.Requests()

    def tearDown(self):
        del self._requests

    def test_adding_one_request(self):
        self._requests.add(1, 2, 3)
        self.assertEqual(len(self._requests.get()), 1)
        self.assertEqual(self._requests.get()[0]['node_id'], 1)
        self.assertEqual(self._requests.get()[0]['resolve_callbacks'], [2])
        self.assertEqual(self._requests.get()[0]['reject_callbacks'], [3])

    def test_adding_same_requests(self):
        self._requests.add(1, 2, 3)
        self._requests.add(1, 2, 3)
        self.assertEqual(len(self._requests.get()), 1)
        self.assertEqual(self._requests.get()[0]['node_id'], 1)
        self.assertEqual(self._requests.get()[0]['resolve_callbacks'], [2])
        self.assertEqual(self._requests.get()[0]['reject_callbacks'], [3])

    def test_adding_requests_with_same_node_id(self):
        self._requests.add(1, 2, 3)
        self._requests.add(1, 4, 5)
        self.assertEqual(len(self._requests.get()), 1)
        self.assertEqual(len(self._requests.get()[0]['resolve_callbacks']), 2)
        self.assertEqual(len(self._requests.get()[0]['reject_callbacks']), 2)
        self.assertEqual(self._requests.get()[0]['node_id'], 1)
        self.assertEqual(self._requests.get()[0]['resolve_callbacks'], [2, 4])
        self.assertEqual(self._requests.get()[0]['reject_callbacks'], [3, 5])

    def test_adding_different_requests(self):
        self._requests.add(1, 2, 3)
        self._requests.add(2, 4, 5)
        self.assertEqual(len(self._requests.get()), 2)
        self.assertEqual(len(self._requests.get()[0]['resolve_callbacks']), 1)
        self.assertEqual(len(self._requests.get()[1]['reject_callbacks']), 1)
        self.assertEqual(self._requests.get()[0]['node_id'], 1)
        self.assertEqual(self._requests.get()[0]['resolve_callbacks'], [2])
        self.assertEqual(self._requests.get()[0]['reject_callbacks'], [3])
        self.assertEqual(self._requests.get()[1]['node_id'], 2)
        self.assertEqual(self._requests.get()[1]['resolve_callbacks'], [4])
        self.assertEqual(self._requests.get()[1]['reject_callbacks'], [5])

    def test_finding_of_node(self):
        self._requests.add(1, 2, 3)
        self._requests.add(2, 4, 5)
        self._requests.add(3, 4, 5)
        request = self._requests.find(2)
        self.assertEqual(request['node_id'], 2)
        self.assertEqual(request['resolve_callbacks'], [4])
        self.assertEqual(request['reject_callbacks'], [5])

    def test_removal_of_node(self):
        self._requests.add(1, 2, 3)
        self._requests.add(2, 4, 5)
        self._requests.add(2, 6, 7)
        self._requests.add(3, 8, 9)
        self._requests.remove(2)
        self.assertEqual(len(self._requests.get()), 2)
        self.assertEqual(self._requests.find(2), None)

    def test_clearing_all_requests(self):
        expected_error = cdp.ConnectionError('foo')
        actual_errors = []
        self._requests.add(1, 2, lambda error: actual_errors.append(error))
        self._requests.add(2, 4, lambda error: actual_errors.append(error))
        self._requests.clear(expected_error)
        self.assertEqual(len(self._requests.get()), 0)
        self.assertEqual(len(actual_errors), 2)
        self.assertEqual(actual_errors[0], expected_error)
        self.assertEqual(actual_errors[1], expected_error)
