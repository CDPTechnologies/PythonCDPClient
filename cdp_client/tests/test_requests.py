from cdp_client import cdp
from promise import Promise
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
        self._requests.add(1, 2)
        self.assertEqual(len(self._requests.get()), 1)
        self.assertEqual(self._requests.get()[0].node_path, 1)
        self.assertEqual(self._requests.get()[0].promises, [2])

    def test_adding_same_requests(self):
        self._requests.add(1, 2)
        self._requests.add(1, 2)
        self.assertEqual(len(self._requests.get()), 1)
        self.assertEqual(self._requests.get()[0].node_path, 1)
        self.assertEqual(self._requests.get()[0].promises, [2])

    def test_adding_requests_with_same_node_id(self):
        self._requests.add(1, 2)
        self._requests.add(1, 4)
        self.assertEqual(len(self._requests.get()), 1)
        self.assertEqual(len(self._requests.get()[0].promises), 2)
        self.assertEqual(self._requests.get()[0].node_path, 1)
        self.assertEqual(self._requests.get()[0].promises, [2, 4])

    def test_adding_different_requests(self):
        self._requests.add(1, 2)
        self._requests.add(2, 4)
        self.assertEqual(len(self._requests.get()), 2)
        self.assertEqual(len(self._requests.get()[0].promises), 1)
        self.assertEqual(self._requests.get()[0].node_path, 1)
        self.assertEqual(self._requests.get()[0].promises, [2])
        self.assertEqual(self._requests.get()[1].node_path, 2)
        self.assertEqual(self._requests.get()[1].promises, [4])

    def test_finding_of_node(self):
        self._requests.add(1, 2)
        self._requests.add(2, 4)
        self._requests.add(3, 4)
        request = self._requests.find(2)
        self.assertEqual(request.node_path, 2)
        self.assertEqual(request.promises, [4])

    def test_removal_of_node(self):
        self._requests.add(1, 2)
        self._requests.add(2, 4)
        self._requests.add(2, 6)
        self._requests.add(3, 8)
        self._requests.remove(2)
        self.assertEqual(len(self._requests.get()), 2)
        self.assertEqual(self._requests.find(2), None)

    def test_clearing_all_requests(self):
        actual_errors = []
        expected_error = cdp.ConnectionError('foo')
        p1 = Promise()
        p2 = Promise()
        p1.catch(lambda error: actual_errors.append(error))
        p2.catch(lambda error: actual_errors.append(error))
        self._requests.add(1, p1)
        self._requests.add(2, p2)
        self._requests.clear(expected_error)
        self.assertEqual(len(self._requests.get()), 0)
        self.assertEqual(len(actual_errors), 2)
        self.assertEqual(actual_errors[0], expected_error)
        self.assertEqual(actual_errors[1], expected_error)
