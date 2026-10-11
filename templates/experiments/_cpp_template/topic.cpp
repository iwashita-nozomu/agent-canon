#include <iostream>
#include <string>

namespace experiment {

struct Request {
  std::string config_path;
  std::string case_id;
};

struct Result {
  std::string raw_output;
};

// The consumer implements this function with its native decode and experiment logic.
Result run(const Request& request);

}  // namespace experiment

int main(int argc, char* argv[]) {
  experiment::Request request;
  bool has_config = false;
  bool has_case_id = false;

  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--config" && !has_config && index + 1 < argc) {
      request.config_path = argv[++index];
      if (request.config_path.empty()) {
        std::cerr << "--config PATH is required\n";
        return 2;
      }
      has_config = true;
    } else if (argument == "--case-id" && !has_case_id && index + 1 < argc) {
      request.case_id = argv[++index];
      if (request.case_id.empty()) {
        std::cerr << "--case-id ID must not be empty\n";
        return 2;
      }
      has_case_id = true;
    } else {
      std::cerr << "usage: <topic> --config PATH [--case-id ID]\n";
      return 2;
    }
  }

  if (!has_config) {
    std::cerr << "--config PATH is required\n";
    return 2;
  }

  const experiment::Result result = experiment::run(request);
  std::cout << result.raw_output;
  return std::cout ? 0 : 1;
}
