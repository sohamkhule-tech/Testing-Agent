import pytest

from app.schemas.test_plan import generate_test_case_id, renumber_scenario_ids


class TestGenerateTestCaseId:
    @pytest.mark.parametrize(
        "index,expected",
        [
            (1, "TC-001"),
            (9, "TC-009"),
            (10, "TC-010"),
            (20, "TC-020"),
            (21, "TC-021"),
            (99, "TC-099"),
            (100, "TC-100"),
            (101, "TC-101"),
            (999, "TC-999"),
            (1000, "TC-1000"),
        ],
    )
    def test_generates_zero_padded_id(self, index, expected):
        assert generate_test_case_id(index) == expected

    def test_sequential_continuity(self):
        ids = [generate_test_case_id(i) for i in range(1, 101)]
        assert ids[0] == "TC-001"
        assert ids[19] == "TC-020"
        assert ids[20] == "TC-021"
        assert ids[98] == "TC-099"
        assert ids[99] == "TC-100"


class TestRenumberScenarioIds:
    @staticmethod
    def _build_module(name, scenarios):
        return {
            "name": name,
            "description": f"{name} description",
            "pages": [f"/{name.lower()}"],
            "scenarios": scenarios,
        }

    @staticmethod
    def _build_scenario(old_id, title, deps=None):
        return {
            "metadata": {
                "id": old_id,
                "title": title,
                "description": f"Desc for {title}",
                "priority": "medium",
                "category": "functional",
                "module": "",
                "dependencies": deps or [],
            },
            "use_cases": [],
        }

    def _extract_ids(self, modules):
        result = []
        for mod in modules:
            for sc in mod["scenarios"]:
                result.append(sc["metadata"]["id"])
        return result

    def test_renumbers_across_multiple_modules(self):
        modules = [
            self._build_module("Module A",
                [self._build_scenario("TC-001", "Login"), self._build_scenario("TC-002", "Dashboard")]),
            self._build_module("Module B",
                [self._build_scenario("TC-101", "Form Submit"), self._build_scenario("TC-102", "Logout")]),
        ]
        all_scenarios = []
        priorities = {"critical_paths": ["TC-001", "TC-102"]}
        reg_candidates = ["TC-101"]
        dep_ids = ["TC-001"]

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        assert self._extract_ids(modules) == ["TC-001", "TC-002", "TC-003", "TC-004"]
        assert priorities["critical_paths"] == ["TC-001", "TC-004"]
        assert reg_candidates == ["TC-003"]
        assert dep_ids == ["TC-001"]

    def test_renumbers_from_llm_gaps(self):
        modules = [
            self._build_module("Login",
                [self._build_scenario(f"TC-{i:03d}", f"Login scenario {i}") for i in range(1, 21)]),
            self._build_module("Dashboard",
                [self._build_scenario(f"TC-{i:03d}", f"Dashboard scenario {i}") for i in range(101, 103)]),
        ]
        all_scenarios = []
        priorities = {"critical_paths": [], "high_priority": [], "medium_priority": [], "low_priority": []}
        reg_candidates = []
        dep_ids = []

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        ids = self._extract_ids(modules)
        assert len(ids) == 22
        assert ids[:20] == [f"TC-{i:03d}" for i in range(1, 21)]
        assert ids[20] == "TC-021"
        assert ids[21] == "TC-022"

    def test_preserves_ids_when_already_sequential(self):
        modules = [
            self._build_module("Mod",
                [self._build_scenario("TC-001", "A"), self._build_scenario("TC-002", "B"), self._build_scenario("TC-003", "C")]),
        ]
        all_scenarios = []
        priorities = {"critical_paths": ["TC-002"]}
        reg_candidates = ["TC-001"]
        dep_ids = ["TC-003"]

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        assert self._extract_ids(modules) == ["TC-001", "TC-002", "TC-003"]
        assert priorities["critical_paths"] == ["TC-002"]
        assert reg_candidates == ["TC-001"]
        assert dep_ids == ["TC-003"]

    def test_unique_ids_across_modules(self):
        modules = [
            self._build_module("A", [self._build_scenario("TC-001", "a1"), self._build_scenario("TC-003", "a2")]),
            self._build_module("B", [self._build_scenario("TC-002", "b1"), self._build_scenario("TC-001", "b2")]),
        ]
        all_scenarios = []
        priorities = {}
        reg_candidates = []
        dep_ids = []

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        ids = self._extract_ids(modules)
        assert len(set(ids)) == len(ids), f"Duplicate IDs found: {ids}"
        assert ids == ["TC-001", "TC-002", "TC-003", "TC-004"]

    def test_updates_scenario_dependencies(self):
        modules = [
            self._build_module("M1",
                [
                    self._build_scenario("TC-001", "Setup", deps=[]),
                    self._build_scenario("TC-101", "Main", deps=["TC-001"]),
                    self._build_scenario("TC-201", "Cleanup", deps=["TC-101"]),
                ]),
        ]
        all_scenarios = []
        priorities = {}
        reg_candidates = []
        dep_ids = []

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        ids = self._extract_ids(modules)
        assert ids == ["TC-001", "TC-002", "TC-003"]
        deps = [sc["metadata"]["dependencies"] for mod in modules for sc in mod["scenarios"]]
        assert deps == [[], ["TC-001"], ["TC-002"]]

    def test_handles_empty_modules(self):
        modules = []
        all_scenarios = []
        priorities = {}
        reg_candidates = []
        dep_ids = []

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        assert modules == []

    def test_handles_scenarios_without_id(self):
        modules = [
            self._build_module("M",
                [
                    {"metadata": {"id": "", "title": "No ID", "dependencies": []}, "use_cases": []},
                    {"metadata": {"id": "TC-099", "title": "Has ID", "dependencies": []}, "use_cases": []},
                ]),
        ]
        all_scenarios = []
        priorities = {}
        reg_candidates = []
        dep_ids = []

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        ids = self._extract_ids(modules)
        assert ids == ["TC-001", "TC-002"]

    def test_benchmark_many_scenarios(self):
        N = 500
        modules = [self._build_module("Large", [self._build_scenario(f"TC-{i:05d}", f"Sc {i}", deps=[]) for i in range(1, N + 1)])]
        all_scenarios = []
        priorities = {"critical_paths": [f"TC-{i:05d}" for i in range(1, N + 1, 10)]}
        reg_candidates = [f"TC-{i:05d}" for i in range(1, N + 1, 7)]
        dep_ids = [f"TC-{i:05d}" for i in range(1, N + 1, 3)]

        renumber_scenario_ids(modules, all_scenarios, priorities, reg_candidates, dep_ids)

        ids = self._extract_ids(modules)
        assert len(ids) == N
        assert ids[0] == "TC-001"
        assert ids[N - 1] == f"TC-{N:03d}"
        assert len(set(ids)) == N
