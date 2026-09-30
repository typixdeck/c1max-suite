#pragma once
#include "protocol.hpp"
#include <functional>
#include <memory>
#include <thread>
#include <utility>

namespace mail {
// Only the owner (UI) thread calls start/take/cancel. The worker owns its result
// until release/acquire completion and join; it never sees widgets or UI state.
class AsyncJob {
public:
    enum class Kind { Receive, Send };
    struct Result { Kind kind=Kind::Receive; bool success=false; std::string error; std::vector<Message> messages; };
private:
    std::unique_ptr<Operation> operation_;
    std::thread worker_;
    std::atomic<bool> done_{false};
    Result result_;
    bool launch(Kind kind,const Options &options,std::function<void(Result&,const Operation&)> work){
        if(busy())return false;
        operation_=std::make_unique<Operation>(options);result_=Result{};result_.kind=kind;done_=false;
        try{
            worker_=std::thread([this,work=std::move(work)]{
                try{work(result_,*operation_);}
                catch(const std::exception&){result_.success=false;result_.error="Mail operation failed; check account settings and retry";}
                catch(...){result_.success=false;result_.error="Mail operation failed";}
                done_.store(true,std::memory_order_release);
            });
        }catch(...){operation_.reset();throw;}
        return true;
    }
public:
    ~AsyncJob(){cancel();if(worker_.joinable())worker_.join();}
    bool busy()const{return bool(operation_);}
    void cancel(){if(operation_)operation_->cancel();}
    bool start_receive(Config config,Options options={}){
        return launch(Kind::Receive,options,[config=std::move(config)](Result &r,const Operation &op){r.success=receive(config,r.messages,r.error,op);});
    }
    bool start_send(Config config,std::string to,std::string subject,std::string body,Options options={}){
        return launch(Kind::Send,options,[config=std::move(config),to=std::move(to),subject=std::move(subject),body=std::move(body)](Result&r,const Operation&op){r.success=send(config,to,subject,body,r.error,op);});
    }
    bool take(Result &result){
        if(!busy()||!done_.load(std::memory_order_acquire))return false;
        worker_.join();result=std::move(result_);operation_.reset();return true;
    }
};
}
