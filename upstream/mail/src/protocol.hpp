#pragma once
#include <atomic>
#include <chrono>
#include <string>
#include <vector>
#include <utility>

namespace mail {
enum class TlsMode { ByPort, Implicit, Upgrade };
struct Config {
    std::string pop_host,pop_port="995",smtp_host,smtp_port="465",username,password,sender;
    TlsMode pop_tls=TlsMode::ByPort,smtp_tls=TlsMode::ByPort;
};
struct Message { std::string from,subject,body; unsigned number=0; };
struct Options {
    int timeout_ms=30000; // One deadline for DNS, connect, TLS and the complete transaction.
    std::string ca_file="/etc/ssl/certs/ca-certificates.crt";
};
class Operation {
    std::atomic<bool> cancelled_{false};
public:
    const Options options;
    const std::chrono::steady_clock::time_point deadline;
    explicit Operation(Options value={}):options(std::move(value)),deadline(std::chrono::steady_clock::now()+std::chrono::milliseconds(options.timeout_ms)){}
    void cancel(){cancelled_.store(true,std::memory_order_relaxed);}
    bool check(std::string &error) const;
};
bool receive(const Config &config,std::vector<Message> &messages,std::string &error,const Operation &operation);
bool send(const Config &config,const std::string &to,const std::string &subject,const std::string &body,std::string &error,const Operation &operation);
#ifdef MAIL_NETWORK_TEST
// Test-only DNS delay: production has no transport/TLS bypass.
void test_resolver_delay(int milliseconds);
#endif
}
