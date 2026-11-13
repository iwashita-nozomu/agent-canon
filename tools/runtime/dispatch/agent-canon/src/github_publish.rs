// @dependency-start
// contract implementation
// responsibility Publishes an explicitly selected Git branch/PR through configured Git and gh transports with immutable identity readback.
// upstream implementation update_lifecycle_contract.rs owns PR lifecycle and gate schemas
// upstream implementation artifacts/artifact_identity.rs owns canonical identity bytes
// upstream design ../../../../../agents/skills/pr-processing.md owns publication workflow
// downstream implementation main.rs exposes github-publish
// @dependency-end

use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::path::{Path,PathBuf};
use std::process::Command;
type Result<T>=std::result::Result<T,Failure>;
const HELP:&str="Publish a GitHub branch or PR with verified remote identity and exact readback.

Usage: agent-canon github-publish [--root ROOT] <push|pr|publish-pr|checks> --user-task TASK [options]

Global:
  --root ROOT             Repository root (default: current directory).
Common action options:
  --user-task TASK        Current user task authorizing the operation (required).
  --repo OWNER/REPO       GitHub repository; otherwise read from gh.
  --remote NAME           Configured Git remote (default: origin).
  --branch NAME           Selected branch (default: current named branch).
  --summary-out PATH      Optional JSON summary beneath the explicit parent root.
PR / publish-pr:
  --base NAME             Base branch (default: main).
  --title TITLE           PR title (required).
  --body-file PATH        UTF-8 PR body file (required).
  --draft                Create a draft PR.
  --update-existing       Update an existing open PR.
push / publish-pr:
  --allow-main            Explicitly permit pushing main.
checks:
  --pr SELECTOR           PR number, URL, or branch.
  --watch                 Wait for checks.
";
#[derive(Debug)]
pub struct CommandResult {pub args:Vec<String>,pub returncode:i32,pub stdout:String,pub stderr:String}
pub trait Runner {fn execute(&mut self,root:&Path,args:&[String])->std::io::Result<CommandResult>;}
pub struct SystemRunner;
impl Runner for SystemRunner {
    fn execute(&mut self,root:&Path,args:&[String])->std::io::Result<CommandResult>{
        let (program,arguments)=args.split_first().ok_or_else(||std::io::Error::new(std::io::ErrorKind::InvalidInput,"command argv required"))?;
        let result=Command::new(program).args(arguments).current_dir(root).output()?;
        #[cfg(unix)] let returncode={use std::os::unix::process::ExitStatusExt;result.status.code().unwrap_or_else(||-result.status.signal().unwrap_or(1))};
        #[cfg(not(unix))] let returncode=result.status.code().unwrap_or(1);
        Ok(CommandResult{args:args.into(),returncode,stdout:String::from_utf8_lossy(&result.stdout).into_owned(),stderr:String::from_utf8_lossy(&result.stderr).into_owned()})
    }
}
#[derive(Debug)]
pub struct Failure {pub message:String,pub next_action:String,pub partial_success:Option<Value>}
fn failure(message:impl Into<String>,next:&str)->Failure{Failure{message:message.into(),next_action:next.into(),partial_success:None}}
fn strings(args:&[&str])->Vec<String>{args.iter().map(|value|(*value).into()).collect()}
fn run_command(runner:&mut impl Runner,root:&Path,args:Vec<String>,next:&str)->Result<CommandResult>{
    let result=runner.execute(root,&args).map_err(|error|failure(error.to_string(),next))?;
    if result.returncode!=0{let details=[result.stderr.trim(),result.stdout.trim()].into_iter().filter(|value|!value.is_empty()).collect::<Vec<_>>().join("\n");let message=format!("command failed ({}): {}{}",result.returncode,result.args.join(" "),if details.is_empty(){String::new()}else{format!("\n{}",details.chars().take(4000).collect::<String>())});return Err(failure(message,next));}Ok(result)
}
fn object(text:&str,command:&str)->Result<Value>{let value:Value=serde_json::from_str(text).map_err(|error|failure(format!("{command} did not return valid JSON: {error}"),"read_the_exact_remote_json_identity"))?;if !value.is_object(){return Err(failure(format!("{command} did not return a JSON object"),"read_the_exact_remote_json_identity"));}Ok(value)}
fn text<'a>(value:&'a Value,key:&str)->&'a str{value.get(key).and_then(Value::as_str).unwrap_or("")}
fn sha(value:&Value)->Result<String>{let bytes=crate::artifacts::artifact_identity::canonical_json_bytes(value).map_err(|error|failure(error.to_string(),"materialize_canonical_publication_evidence"))?;Ok(format!("sha256:{:x}",Sha256::digest(bytes)))}
fn evidence_ref(value:&Value)->Result<String>{Ok(format!("evidence:{}",sha(value)?.strip_prefix("sha256:").expect("hash prefix")))}
fn is_oid(value:&str)->bool{value.len()==40&&value.bytes().all(|byte|byte.is_ascii_digit()||matches!(byte,b'a'..=b'f'))}
fn clean_slug(value:&str)->Option<String>{let value=value.trim().strip_suffix(".git").unwrap_or(value.trim()).trim_matches('/');let parts=value.split('/').filter(|part|!part.is_empty()).collect::<Vec<_>>();if parts.len()<2{None}else{Some(parts[parts.len()-2..].join("/"))}}
pub fn normalized_repo_slug(value:&str)->Option<String>{
    let value=crate::python_text::python_strip(value);if value.is_empty(){return None;}
    static SCP:std::sync::LazyLock<regex::Regex>=std::sync::LazyLock::new(||regex::Regex::new(r"^[^@]+@[^:]+:(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$").expect("SCP remote grammar"));
    if let Some(capture)=SCP.captures(value){return clean_slug(&capture["slug"]);}
    if let Some((scheme,remainder))=value.split_once("://"){if ["http","https","ssh"].contains(&scheme){let path=remainder.find('/').map(|index|&remainder[index..])?;return clean_slug(path.split(['?','#']).next().unwrap_or(path));}}
    if value.contains('/')&&!value.contains("://")&&!value.contains(':'){return clean_slug(value);}None
}
#[derive(Clone,Debug)]
pub struct RemoteVerification {pub repo:String,pub remote:String,pub remote_url:String,pub remote_slug:String,pub topology_kind:String,pub head_repo:String,pub fork_parent_repo:String,pub permission_state:String,pub permission_evidence_id:String,pub actor_id:String,pub actor_display_name:String}
fn repo_metadata(runner:&mut impl Runner,root:&Path,repo:Option<&str>,fork:bool)->Result<Value>{let mut command=strings(&["gh","repo","view"]);if let Some(repo)=repo{command.push(repo.into());}command.extend(strings(&["--json",if fork{"nameWithOwner,url,sshUrl,viewerPermission,parent"}else{"nameWithOwner,url,sshUrl,viewerPermission"}]));object(&run_command(runner,root,command,"authenticate_gh_and_verify_the_target_repository")?.stdout,"gh repo view")}
pub fn verify_remote(runner:&mut impl Runner,root:&Path,repo:Option<&str>,remote:&str)->Result<RemoteVerification>{
    let metadata=repo_metadata(runner,root,repo,false)?;let repo=text(&metadata,"nameWithOwner");if !repo.contains('/'){return Err(failure("gh repo view did not expose nameWithOwner","authenticate_gh_and_verify_the_target_repository"));}
    let remote_url=run_command(runner,root,strings(&["git","remote","get-url",remote]),"configure_origin_remote_for_the_user_task")?.stdout.trim().to_owned();let remote_slug=normalized_repo_slug(&remote_url).ok_or_else(||failure(format!("remote {remote:?} has an unrecognized GitHub identity"),"fix_origin_remote_or_pass_the_correct_--repo_verified_remote_required"))?;
    let (kind,parent,permission)=if remote_slug==repo{("user",String::new(),metadata.clone())}else{let head=repo_metadata(runner,root,Some(&remote_slug),true)?;if text(&head,"nameWithOwner")!=remote_slug||head.get("parent").map(|value|text(value,"nameWithOwner"))!=Some(repo){return Err(failure(format!("remote {remote:?} points at {remote_slug}, which is not a verified fork of {repo}"),"materialize_the_typed_multiple_remotes_or_contributor_lifecycle"));}("fork",repo.into(),head)};
    let viewer=permission.get("viewerPermission").cloned().unwrap_or(Value::Null);let state=match viewer.as_str(){Some("ADMIN"|"MAINTAIN"|"WRITE")=>"verified_true",Some(_)=>"verified_false",None=>"unknown"};
    let permission_evidence=json!({"repo":repo,"head_repo":remote_slug,"topology_kind":kind,"remote":remote,"remote_url_sha256":format!("sha256:{:x}",Sha256::digest(remote_url.as_bytes())),"viewer_permission":viewer,"permission_state":state,"authority_source":"gh repo view viewerPermission"});
    let actor=object(&run_command(runner,root,strings(&["gh","api","user","--jq","{id: .id, login: .login, name: .name}"]),"authenticate_gh_and_read_the_verified_actor_identity")?.stdout,"gh api user")?;
    let actor_id=actor.get("id").and_then(Value::as_i64).ok_or_else(||failure("gh api user did not expose immutable actor identity","authenticate_gh_and_read_the_verified_actor_identity"))?;let login=text(&actor,"login");if login.is_empty(){return Err(failure("gh api user did not expose immutable actor identity","authenticate_gh_and_read_the_verified_actor_identity"));}
    Ok(RemoteVerification{repo:repo.into(),remote:remote.into(),remote_url,remote_slug:remote_slug.clone(),topology_kind:kind.into(),head_repo:remote_slug,fork_parent_repo:parent,permission_state:state.into(),permission_evidence_id:evidence_ref(&permission_evidence)?,actor_id:format!("github-user:{actor_id}"),actor_display_name:if text(&actor,"name").is_empty(){login.into()}else{text(&actor,"name").into()}})
}
#[derive(Default)]
struct Options {root:PathBuf,action:String,user_task:Option<String>,repo:Option<String>,remote:String,branch:Option<String>,summary:Option<PathBuf>,allow_main:bool,base:String,title:Option<String>,body:Option<PathBuf>,draft:bool,update:bool,pr:Option<String>,watch:bool}
enum Parsed {Help,Run(Box<Options>)}
fn parse_options(args:&[String])->std::result::Result<Parsed,String>{
    let options=[("--root",0),("--user-task",1),("--repo",2),("--remote",3),("--branch",4),("--summary-out",5),("--allow-main",6),("--base",7),("--title",8),("--body-file",9),("--draft",10),("--update-existing",11),("--pr",12),("--watch",13),("--help",14)];let mut result=Options{root:".".into(),remote:"origin".into(),base:"main".into(),..Options::default()};let mut index=0;
    while index<args.len(){let raw=&args[index];if raw=="-h"{return Ok(Parsed::Help);}if !raw.starts_with('-'){if result.action.is_empty()&&["push","pr","publish-pr","checks"].contains(&raw.as_str()){result.action=raw.clone();index+=1;continue;}return Err(format!("unrecognized argument: {raw}"));}
        let (option,inline)=raw.split_once('=').map_or((raw.as_str(),None),|(name,value)|(name,Some(value)));let available=options.iter().copied().filter(|(_,key)|if result.action.is_empty(){[0,14].contains(key)}else{*key!=0}).collect::<Vec<_>>();let key=crate::python_cli_options::resolve_long_option_prefix(option,&available).map_err(|_|format!("unrecognized or ambiguous argument: {raw}"))?;if key==14{return Ok(Parsed::Help);}
        let before=result.action.is_empty();let allowed=if before{key==0}else{match key{0=>false,6=>["push","publish-pr"].contains(&result.action.as_str()),7..=11=>["pr","publish-pr"].contains(&result.action.as_str()),12|13=>result.action=="checks",_=>true}};if !allowed{return Err(format!("unrecognized argument: {raw}"));}
        if [6,10,11,13].contains(&key){if inline.is_some(){return Err(format!("argument {option}: ignored explicit argument"));}match key{6=>result.allow_main=true,10=>result.draft=true,11=>result.update=true,13=>result.watch=true,_=>unreachable!(),}index+=1;continue;}
        let value=match inline{Some(value)=>value.to_owned(),None=>{index+=1;args.get(index).cloned().ok_or_else(||format!("argument {option}: expected one argument"))?}};match key{0=>result.root=value.into(),1=>result.user_task=Some(value),2=>result.repo=Some(value),3=>result.remote=value,4=>result.branch=Some(value),5=>if !value.is_empty(){result.summary=Some(value.into());},7=>result.base=value,8=>result.title=Some(value),9=>result.body=Some(value.into()),12=>result.pr=Some(value),_=>unreachable!(),}index+=1;
    }
    if result.action.is_empty(){return Err("the following arguments are required: action".into());}if result.user_task.is_none(){return Err("the following arguments are required: --user-task".into());}if ["pr","publish-pr"].contains(&result.action.as_str())&&(result.title.is_none()||result.body.is_none()){return Err("the following arguments are required: --title, --body-file".into());}Ok(Parsed::Run(Box::new(result)))
}
fn local_identity(runner:&mut impl Runner,root:&Path)->Result<Value>{let branch=run_command(runner,root,strings(&["git","branch","--show-current"]),"checkout_the_selected_named_branch_before_publication")?.stdout.trim().to_owned();if branch.is_empty(){return Err(failure("cannot publish a detached HEAD","checkout_the_selected_named_branch_before_publication"));}let commit=git_oid(runner,root,"HEAD")?;let tree=git_oid(runner,root,"HEAD^{tree}")?;Ok(json!({"branch":branch,"ref":format!("refs/heads/{branch}"),"commit_sha":commit,"tree_sha":tree}))}
fn git_oid(runner:&mut impl Runner,root:&Path,revision:&str)->Result<String>{let value=run_command(runner,root,strings(&["git","rev-parse",revision]),"freeze_the_local_candidate_before_github_publication")?.stdout.trim().to_owned();if !is_oid(&value){return Err(failure("git did not expose an exact commit/tree identity","freeze_the_local_candidate_before_github_publication"));}Ok(value)}
fn permission_identity(verification:&RemoteVerification)->Value{json!({"actor_id":verification.actor_id,"permission_state":verification.permission_state,"permission_evidence_id":verification.permission_evidence_id,"authority_source":"verified gh repository metadata","assumption_forbidden":true})}
fn base_summary(options:&Options,verification:&RemoteVerification,branch:&str)->Value{json!({"user_task":options.user_task,"remote_verified":true,"repo":verification.repo,"remote":verification.remote,"remote_url":verification.remote_url,"branch":branch,"permission_state":verification.permission_state,"permission_evidence_id":verification.permission_evidence_id,"verified_remote_policy":"gh_verified_remote_required"})}

fn validate_lifecycle(value:&Value)->Result<Value>{crate::update_lifecycle_contract::validate_pull_request_lifecycle(value).map_err(|error|failure(error.to_string(),"derive_the_local_candidate_and_verified_base_lifecycle"))}
fn observed_at()->String{let now=time::OffsetDateTime::now_utc();let micro=now.nanosecond()/1000;let base=format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",now.year(),now.month() as u8,now.day(),now.hour(),now.minute(),now.second());if micro==0{format!("{base}Z")}else{format!("{base}.{micro:06}Z")}}
fn body_file(options:&Options)->Result<PathBuf>{let raw=options.body.as_ref().ok_or_else(||failure("PR body file is required","write_the_pr_body_to_a_file"))?;let path=options.root.join(raw).canonicalize().map_err(|error|failure(error.to_string(),"write_the_pr_body_to_a_file"))?;if !path.is_file(){return Err(failure("PR body path is not a file","write_the_pr_body_to_a_file"));}Ok(path)}
fn github_base_identity(runner:&mut impl Runner,root:&Path,repo:&str,reference:&str)->Result<(String,String)>{let endpoint=format!("repos/{repo}/commits/{reference}");let value=object(&run_command(runner,root,strings(&["gh","api",&endpoint,"--jq","{commit_sha: .sha, tree_sha: .commit.tree.sha}"]),"read_the_exact_pull_request_base_commit_and_tree")?.stdout,"gh api base commit")?;let commit=text(&value,"commit_sha");let tree=text(&value,"tree_sha");if !is_oid(commit)||!is_oid(tree){return Err(failure("GitHub base identity is incomplete","read_the_exact_pull_request_base_commit_and_tree"));}Ok((commit.into(),tree.into()))}
fn build_lifecycle(options:&Options,runner:&mut impl Runner,verification:&RemoteVerification,branch:&str)->Result<Value>{
    let candidate=git_oid(runner,&options.root,branch)?;let tree=git_oid(runner,&options.root,&format!("{candidate}^{{tree}}"))?;
    let (base,base_tree)=if verification.topology_kind=="user"&&verification.remote_slug==verification.repo{let reference=format!("{}/{}",verification.remote,options.base);let base=git_oid(runner,&options.root,&reference)?;let tree=git_oid(runner,&options.root,&format!("{base}^{{tree}}"))?;(base,tree)}else{github_base_identity(runner,&options.root,&verification.repo,&options.base)?};
    let body=std::fs::read_to_string(body_file(options)?).map_err(|error|failure(error.to_string(),"write_the_pr_body_to_a_file"))?;let permission=permission_identity(verification);
    let input=json!({"user_task":options.user_task,"title":options.title,"body_sha256":sha(&json!(body))?,"repo":verification.repo,"head_repo":verification.head_repo,"remote":verification.remote,"branch":branch,"base":options.base,"kind":verification.topology_kind});let input_digest=sha(&input)?;
    let transaction=sha(&json!({"input_digest":input_digest,"candidate_sha":candidate,"tree_sha":tree}))?.replacen("sha256:","tx:",1);let snapshot=sha(&json!({"remote":verification.remote,"base_ref":options.base,"base_sha":base,"base_tree":base_tree}))?.replacen("sha256:","snapshot:",1);
    let seed=json!({"transaction_id":transaction,"snapshot_id":snapshot,"candidate_sha":candidate,"tree_sha":tree,"input_digest":input_digest,"permission":permission});let at=observed_at();
    let binding=json!({"transaction_id":transaction,"snapshot_id":snapshot,"candidate_sha":candidate,"tree_sha":tree,"input_digest":input_digest,"tool_id":"github-publish","tool_version":"agent-canon.pull-request-lifecycle.v1","evidence_ref":evidence_ref(&seed)?,"evidence_digest":sha(&seed)?,"timing":{"started_at":at,"finished_at":at,"last_attempt_at":at,"duration_ms":0,"attempt":1,"replayed":false}});
    let (owner,name)=verification.repo.split_once('/').ok_or_else(||failure("repository identity is incomplete","verify_the_target_repository"))?;let (head_owner,head_name)=verification.head_repo.split_once('/').ok_or_else(||failure("head repository identity is incomplete","verify_the_target_repository"))?;
    let state=match verification.permission_state.as_str(){"unknown"=>"permission_unknown","verified_false"=>"permission_denied",_=>if options.draft{"draft"}else{"ready"}};
    let essence=evidence_ref(&json!({"problem":options.user_task,"title":options.title,"body_sha256":sha(&json!(body))?}))?;
    let mut lifecycle=json!({"schema":"agent-canon.pull-request-lifecycle.v1","kind":verification.topology_kind,"binding":binding,"state":state,"remote_identity":{"repo_owner":head_owner,"repo_name":head_name,"remote_name":verification.remote,"url_digest":sha(&json!(verification.remote_url))?,"ref":format!("refs/heads/{branch}"),"commit_sha":candidate,"tree_sha":tree},"base_identity":{"repo_owner":owner,"repo_name":name,"ref":format!("refs/heads/{}",options.base),"commit_sha":base,"tree_sha":base_tree},"head_identity":{"repo_owner":head_owner,"repo_name":head_name,"ref":format!("refs/heads/{branch}"),"commit_sha":candidate,"tree_sha":tree},"branch":crate::update_lifecycle_contract::pull_request_branch_table(),"permission_identity":permission,"pr_essence":{"problem":options.user_task,"intent":options.title.as_deref().filter(|value|!value.is_empty()).or(options.user_task.as_deref()),"canonical_owner":"agents/skills/pr-processing.md","contract_delta":options.title.as_deref().filter(|value|!value.is_empty()).or(options.user_task.as_deref()),"evidence_refs":[essence]},"reviews":[]});
    if verification.topology_kind=="user"{lifecycle["user_identity"]=json!({"actor_id":verification.actor_id,"display_name":verification.actor_display_name});}else{let (parent_owner,parent_name)=verification.fork_parent_repo.split_once('/').ok_or_else(||failure("fork parent repository is incomplete","verify_the_fork_parent"))?;lifecycle["fork_identity"]=json!({"repo_owner":head_owner,"repo_name":head_name,"parent_repo_owner":parent_owner,"parent_repo_name":parent_name,"ref":format!("refs/heads/{branch}")});}validate_lifecycle(&lifecycle)
}
fn remote_head(runner:&mut impl Runner,root:&Path,remote:&str,reference:&str,expected:&str)->Result<String>{let result=run_command(runner,root,strings(&["git","ls-remote",remote,reference]),"read_back_the_exact_remote_branch_commit")?;let records=result.stdout.lines().filter(|line|!line.trim().is_empty()).map(|line|line.split_whitespace().collect::<Vec<_>>()).collect::<Vec<_>>();if records.len()!=1||records[0].len()!=2||records[0][1]!=reference||!is_oid(records[0][0]){return Err(failure("remote branch readback did not return one exact ref identity","reject_remote_publication_and_preserve_the_local_identity"));}if records[0][0]!=expected{return Err(failure(format!("remote branch readback SHA differs from local candidate: expected {expected}, received {}",records[0][0]),"reject_remote_publication_and_preserve_the_local_identity"));}Ok(records[0][0].into())}
fn perform_push(options:&Options,runner:&mut impl Runner,verification:&RemoteVerification,branch:&str,lifecycle:Option<&Value>)->Result<Value>{
    if branch=="main"&&!options.allow_main{return Err(failure("refusing to push main without --allow-main","publish_a_topic_branch_or_pass_--allow-main_with_explicit_user_authority"));}
    let before=local_identity(runner,&options.root)?;if text(&before,"branch")!=branch{return Err(failure("current local branch/ref differs from selected branch","checkout_the_selected_named_branch_before_publication"));}
    if let Some(lifecycle)=lifecycle{let checked=validate_lifecycle(lifecycle)?;if !["draft","ready","changes_requested","external_review"].contains(&text(&checked,"state")){return Err(failure(format!("PR lifecycle state does not permit push: {}",text(&checked,"state")),"resolve_permission_remote_or_successor_state_before_push"));}if checked["head_identity"]["commit_sha"]!=before["commit_sha"]||checked["head_identity"]["tree_sha"]!=before["tree_sha"]{return Err(failure("local branch/ref/commit/tree differs from verified lifecycle head identity","materialize_a_successor_lifecycle_for_the_current_local_commit"));}}
    let dirty=!run_command(runner,&options.root,strings(&["git","status","--short","--untracked-files=all"]),"inspect_the_selected_worktree")?.stdout.trim().is_empty();let reference=format!("refs/heads/{branch}");let destination=format!("{}:{reference}",text(&before,"commit_sha"));let command=strings(&["git","push","-u",&verification.remote,&destination]);
    let result=run_command(runner,&options.root,command.clone(),"fix_git_push_auth_or_remote_before_retrying_verified_push")?;let after=local_identity(runner,&options.root)?;let remote=remote_head(runner,&options.root,&verification.remote,&reference,text(&before,"commit_sha"))?;if after!=before{return Err(failure("local branch, commit, or tree changed across the push","preserve_the_exact_pushed_identity_and_investigate_local_mutation"));}
    let mut summary=base_summary(options,verification,branch);summary.as_object_mut().expect("summary object").extend(json!({"action":"push","publication_boundary":if lifecycle.is_some(){"verified_lifecycle"}else{"branch_transport_only"},"worktree_dirty":dirty,"command":command,"git_push_stdout":result.stdout.trim(),"git_push_stderr":result.stderr.trim(),"local_commit_sha":before["commit_sha"],"local_tree_sha":before["tree_sha"],"remote_readback_sha":remote,"remote_readback_ref":reference,"local_identity_before_push":before,"local_identity_after_push":after,"status":"ok"}).as_object().expect("push summary").clone());if let Some(lifecycle)=lifecycle{summary["pull_request_lifecycle"]=lifecycle.clone();}Ok(summary)
}

pub fn pull_request_readback(runner:&mut impl Runner,root:&Path,repo:&str,selector:&str)->Result<Value>{
    let cli=run_command(runner,root,strings(&["gh","pr","view",selector,"--repo",repo,"--json","number,url,state,isDraft,baseRefName,headRefName,headRefOid,headRepository,reviewDecision,reviews,mergeCommit"]),"read_back_the_exact_pull_request_identity")?;let mut readback=object(&cli.stdout,"gh pr view")?;let number=readback.get("number").and_then(Value::as_u64).ok_or_else(||failure("pull request readback did not return a numeric PR number","read_back_the_exact_pull_request_identity"))?;
    let endpoint=format!("repos/{repo}/pulls/{number}");let api=object(&run_command(runner,root,strings(&["gh","api",&endpoint,"--jq","{number: .number, url: .html_url, state: .state, isDraft: .draft, merged: .merged, mergeCommitOid: .merge_commit_sha, baseRefName: .base.ref, baseRefOid: .base.sha, headRefName: .head.ref, headRefOid: .head.sha, headRepository: .head.repo.full_name}"]),"read_back_the_exact_pull_request_identity")?.stdout,"gh api pull request")?;
    let state=text(&api,"state").to_uppercase();let merged=api.get("merged").and_then(Value::as_bool);let remote_state=if merged==Some(true){"MERGED"}else{state.as_str()};let merge_oid=readback.get("mergeCommit").map(|value|text(value,"oid")).filter(|value|!value.is_empty()).map(str::to_owned);
    let head_repo=readback.get("headRepository").map(|value|text(value,"nameWithOwner")).filter(|value|!value.is_empty());let api_merge=api.get("mergeCommitOid").and_then(Value::as_str);
    let matches=api.get("number")==readback.get("number")&&api.get("url").is_some_and(Value::is_string)&&api.get("url")==readback.get("url")&&api.get("baseRefName")==readback.get("baseRefName")&&is_oid(text(&api,"baseRefOid"))&&api.get("headRefName")==readback.get("headRefName")&&is_oid(text(&api,"headRefOid"))&&api.get("headRefOid")==readback.get("headRefOid")&&api.get("headRepository").and_then(Value::as_str)==head_repo&&["OPEN","CLOSED"].contains(&state.as_str())&&merged.is_some()&&(merged!=Some(true)||state=="CLOSED")&&remote_state==text(&readback,"state").to_uppercase()&&api.get("isDraft").is_some_and(Value::is_boolean)&&readback.get("isDraft").is_some_and(Value::is_boolean)&&api.get("isDraft")==readback.get("isDraft")&&if merged==Some(true){api_merge.is_some_and(is_oid)&&api_merge==merge_oid.as_deref()}else{merge_oid.is_none()&&api_merge.is_none_or(is_oid)};
    if !matches{return Err(failure("pull request API identity differs from CLI readback","reject_publication_readback_and_retry_exact_PR_identity"));}
    readback["baseRefOid"]=api["baseRefOid"].clone();
    if let Some(merge)=merge_oid{
        let endpoint=format!("repos/{repo}/git/commits/{merge}");let identity=object(&run_command(runner,root,strings(&["gh","api",&endpoint,"--jq","{commit_sha: .sha, tree_sha: .tree.sha, parents: [.parents[].sha]}"]),"read_back_the_exact_publication_merge_tree")?.stdout,"gh api merge commit")?;
        if text(&identity,"commit_sha")!=merge||!is_oid(text(&identity,"tree_sha")){return Err(failure("merge commit API identity differs from PR readback or tree is incomplete","read_back_the_exact_publication_merge_tree"));}
        let parent=identity.get("parents").and_then(Value::as_array).and_then(|values|values.first()).and_then(Value::as_str).filter(|value|is_oid(value)).ok_or_else(||failure("merge commit lacks an authoritative pre-merge CAS parent","read_back_the_exact_publication_merge_base"))?;
        let endpoint=format!("repos/{repo}/git/commits/{parent}");let base=object(&run_command(runner,root,strings(&["gh","api",&endpoint,"--jq","{commit_sha: .sha, tree_sha: .tree.sha}"]),"read_back_the_exact_publication_merge_base_tree")?.stdout,"gh api merge CAS base commit")?;
        if text(&base,"commit_sha")!=parent||!is_oid(text(&base,"tree_sha")){return Err(failure("merge CAS base commit/tree identity is incomplete","read_back_the_exact_publication_merge_base_tree"));}
        readback["mergeTreeOid"]=identity["tree_sha"].clone();readback["mergeCasBaseOid"]=json!(parent);readback["mergeCasBaseTreeOid"]=base["tree_sha"].clone();
    }else{for key in ["mergeTreeOid","mergeCasBaseOid","mergeCasBaseTreeOid"]{readback[key]=Value::Null;}}Ok(readback)
}
pub fn lifecycle_with_pr_readback(lifecycle:&Value,readback:&Value)->Result<Value>{
    let checked=validate_lifecycle(lifecycle)?;let base=&checked["base_identity"];let head=&checked["head_identity"];let state=text(readback,"state").to_uppercase();
    if text(readback,"baseRefName")!=text(base,"ref").trim_start_matches("refs/heads/"){return Err(failure("pull request base identity changed after publication","materialize_a_conflict_successor_lifecycle"));}
    if state!="MERGED"&&readback.get("baseRefOid")!=base.get("commit_sha"){return Err(failure("pull request base commit changed after publication","materialize_a_conflict_successor_lifecycle"));}
    if text(readback,"headRefName")!=text(head,"ref").trim_start_matches("refs/heads/")||readback.get("headRefOid")!=head.get("commit_sha"){return Err(failure("pull request head ref/commit differs from the frozen candidate","materialize_a_conflict_successor_lifecycle"));}
    if readback.get("headRepository").map(|value|text(value,"nameWithOwner"))!=Some(format!("{}/{}",text(head,"repo_owner"),text(head,"repo_name")).as_str()){return Err(failure("pull request head repository changed after publication","materialize_a_conflict_successor_lifecycle"));}
    let next=if state=="MERGED"{if !readback.get("mergeCommit").is_some_and(|value|is_oid(text(value,"oid")))||!is_oid(text(readback,"mergeTreeOid"))||readback.get("mergeCasBaseOid")!=base.get("commit_sha")||readback.get("mergeCasBaseTreeOid")!=base.get("tree_sha"){return Err(failure("merged PR readback lacks matching merge/CAS identity","reject_publication_readback_and_materialize_a_successor"));}"merged"}else if state=="CLOSED"{"closed_head"}else if readback.get("isDraft")==Some(&Value::Bool(true)){"draft"}else{match text(readback,"reviewDecision").to_uppercase().as_str(){"CHANGES_REQUESTED"=>"changes_requested","REVIEW_REQUIRED"=>"external_review",_=>"ready"}};
    let mut reviews=checked.get("reviews").and_then(Value::as_array).cloned().unwrap_or_default();if let Some(remote)=readback.get("reviews").and_then(Value::as_array){for (index,value) in remote.iter().enumerate().filter(|(_,value)|value.is_object()){let reviewer=value.get("author").map(|value|text(value,"login")).filter(|value|!value.is_empty()).unwrap_or("unknown");let raw=text(value,"state").to_lowercase();let state=if ["approved","changes_requested","commented","dismissed"].contains(&raw.as_str()){raw.as_str()}else{"commented"};let review=json!({"review_id":value.get("id").and_then(Value::as_str).filter(|value|!value.is_empty()).map(str::to_owned).unwrap_or_else(||format!("readback:{index}:{reviewer}")),"reviewer_id":reviewer,"state":state,"body_digest":sha(&json!(text(value,"body")))?});if !reviews.contains(&review){reviews.push(review);}}}
    let mut updated=checked.clone();updated["state"]=json!(next);updated["reviews"]=json!(reviews);let reference=evidence_ref(&json!({"predecessor_evidence_ref":updated["binding"]["evidence_ref"],"readback":readback,"state":next,"reviews":reviews}))?;updated["binding"]["evidence_ref"]=json!(reference);updated["binding"]["evidence_digest"]=json!(reference.replacen("evidence:","sha256:",1));
    crate::update_lifecycle_contract::validate_pull_request_transition(&checked,&updated).map_err(|error|failure(error.to_string(),"materialize_a_successor_lifecycle_for_the_changed_remote_identity"))
}
fn existing_pr(runner:&mut impl Runner,root:&Path,repo:&str,branch:&str)->Result<Option<Value>>{let output=run_command(runner,root,strings(&["gh","pr","list","--repo",repo,"--head",branch,"--state","open","--json","number,url,title,headRefName,baseRefName"]),"authenticate_gh_and_inspect_existing_pull_requests")?;let values:Value=serde_json::from_str(&output.stdout).map_err(|error|failure(error.to_string(),"authenticate_gh_and_inspect_existing_pull_requests"))?;let values=values.as_array().ok_or_else(||failure("gh pr list did not return a JSON array","authenticate_gh_and_inspect_existing_pull_requests"))?;if values.iter().any(|value|!value.is_object()){return Err(failure("gh pr list did not return a list of JSON objects","authenticate_gh_and_inspect_existing_pull_requests"));}Ok(values.first().cloned())}
fn mutation_evidence(options:&Options,verification:&RemoteVerification,branch:&str,lifecycle:&Value,action:&str,url:&str,number:Option<u64>)->Value{
    let selector=if url.is_empty(){number.map(|number|number.to_string()).unwrap_or_else(||branch.into())}else{url.into()};
    let mut value=json!({"action":options.action,"remote_verified":true,"repo":verification.repo,"remote":verification.remote,"branch":branch,"mutation_completed":true,"mutation_action":action,"pr_selector":selector,"expected_pr_head_ref":text(&lifecycle["head_identity"],"ref").trim_start_matches("refs/heads/"),"expected_pr_head_sha":lifecycle["head_identity"]["commit_sha"],"expected_pr_base_ref":text(&lifecycle["base_identity"],"ref").trim_start_matches("refs/heads/"),"expected_pr_base_sha":lifecycle["base_identity"]["commit_sha"],"recovery_mode":"readback_only"});if !url.is_empty(){value["pr_url"]=json!(url);}if let Some(number)=number{value["pr_number"]=json!(number);}value
}
fn pr_number(url:&str)->Option<u64>{let path=url.split(['?','#']).next().unwrap_or(url).trim_end_matches('/');let (prefix,number)=path.rsplit_once('/')?;if !prefix.ends_with("/pull"){return None;}number.parse::<u64>().ok().filter(|number|*number>0)}
fn perform_pr(options:&Options,runner:&mut impl Runner,verification:&RemoteVerification,branch:&str,lifecycle:&Value)->Result<Value>{
    let body=body_file(options)?;let lifecycle=validate_lifecycle(lifecycle)?;if !["draft","ready","changes_requested","external_review"].contains(&text(&lifecycle,"state")){return Err(failure(format!("PR lifecycle state does not permit PR mutation: {}",text(&lifecycle,"state")),"resolve_permission_remote_or_successor_state_before_pr_mutation"));}
    let existing=existing_pr(runner,&options.root,&verification.repo,branch)?;let mut summary=base_summary(options,verification,branch);
    let (action,url,number,command,stdout,mutated)=if let Some(existing)=existing{let number=existing.get("number").and_then(Value::as_u64);let url=text(&existing,"url").to_owned();if let Some(selected_number)=number.filter(|_|options.update){let selector=selected_number.to_string();let command=strings(&["gh","pr","edit",&selector,"--repo",&verification.repo,"--title",options.title.as_deref().unwrap_or(""),"--body-file",&body.to_string_lossy()]);let output=run_command(runner,&options.root,command.clone(),"fix_gh_pr_edit_auth_or_update_the_pr_body_manually")?;("pr-update",url,number,Some(command),Some(output.stdout.trim().to_owned()),true)}else{("pr-existing",url,number,None,None,false)}}else{
        let mut command=strings(&["gh","pr","create","--repo",&verification.repo,"--base",&options.base,"--head",branch,"--title",options.title.as_deref().unwrap_or(""),"--body-file",&body.to_string_lossy()]);if options.draft{command.push("--draft".into());}let output=run_command(runner,&options.root,command.clone(),"fix_gh_pr_create_auth_or_repository_permissions_before_retrying_verified_pr_create")?;let url=output.stdout.trim().to_owned();let number=pr_number(&url);("pr-create",url,number,Some(command),None,true)
    };
    let selector=if action=="pr-create"{branch.to_owned()}else{number.map(|number|number.to_string()).unwrap_or_else(||branch.to_owned())};let partial=mutation_evidence(options,verification,branch,&lifecycle,action,&url,number);
    let readback=pull_request_readback(runner,&options.root,&verification.repo,&selector).and_then(|readback|lifecycle_with_pr_readback(&lifecycle,&readback).map(|lifecycle|(readback,lifecycle))).map_err(|mut error|{if mutated{error.partial_success=Some(partial);}error})?;
    summary.as_object_mut().expect("summary object").extend(json!({"action":action,"status":"ok","pr_url":url,"pr_number":if action=="pr-create"{readback.0.get("number").cloned().unwrap_or(Value::Null)}else{json!(number)},"pull_request_lifecycle":readback.1}).as_object().expect("PR summary").clone());if let Some(command)=command{summary["command"]=json!(command);}if let Some(stdout)=stdout{summary["gh_stdout"]=json!(stdout);}if action=="pr-existing"{summary["next_action"]=json!("use_existing_pr_or_pass_--update-existing");}Ok(summary)
}

pub fn materialize_pr_identity_gate(owner_root:&Path,lifecycle:&Value,cas:&Value,rebind:&Value,upstream:&[Value])->Result<Value>{
    use crate::update_lifecycle_contract as lifecycle_api;
    let error=|error:lifecycle_api::LifecycleContractError|failure(error.to_string(),"materialize_the_exact_candidate_permission_and_cas_evidence");
    let rebind=lifecycle_api::validate_source_main_rebind_receipt(rebind).map_err(error)?;let cas=lifecycle_api::validate_candidate_cas_rebind_transition(&rebind,cas).map_err(error)?;let lifecycle=lifecycle_api::validate_candidate_cas_pr_transition(&cas,lifecycle).map_err(error)?;
    let upstream=lifecycle_api::validate_gate_chain(upstream,Some(&["G1","G2"]),true).map_err(error)?;let identity=lifecycle_api::binding_identity(&lifecycle["binding"]).map_err(error)?;
    for gate in &upstream{if lifecycle_api::binding_identity(&gate["binding"]).map_err(error)?!=identity{return Err(failure("G1/G2/CAS evidence does not bind selected PR topology","materialize_a_successor_for_the_changed_candidate_or_base"));}}
    if lifecycle["permission_identity"]["permission_state"]!="verified_true"{return Err(failure("push permission is not verified true for this immutable PR topology","read_verified_remote_permission_and_create_a_successor_lifecycle"));}
    let mut references=upstream.iter().map(|gate|text(&gate["binding"],"evidence_ref").to_owned()).collect::<Vec<_>>();references.push(text(&cas["binding"],"evidence_ref").into());references.push(text(&lifecycle["binding"],"evidence_ref").into());
    // The v1 record retains its published owner identifier across the language migration.
    let input=lifecycle_api::GateVerdictInput{binding:lifecycle["binding"].clone(),gate_id:"G3".into(),ordered_input_evidence_refs:references,invariant:"pr_identity_cas".into(),output_digest:sha(&json!({"lifecycle":lifecycle,"cas":cas,"source_main_rebind":rebind}))?,owner:format!("{}#materialize_pr_identity_gate",owner_root.join("tools/repository/github/github_publish.py").display()),verdict:"pass".into(),retry_reason:None,next_checkpoint:None};
    lifecycle_api::materialize_gate_verdict(&input).map_err(error)
}
pub fn require_pr_identity_gate(lifecycle:&Value,cas:&Value,rebind:&Value,upstream:&[Value],gate:&Value)->Result<(Value,Value)>{
    use crate::update_lifecycle_contract as lifecycle_api;let error=|error:lifecycle_api::LifecycleContractError|failure(error.to_string(),"materialize_G1_G2_and_CAS_for_the_exact_candidate");
    let rebind=lifecycle_api::validate_source_main_rebind_receipt(rebind).map_err(error)?;let cas=lifecycle_api::validate_candidate_cas_rebind_transition(&rebind,cas).map_err(error)?;let lifecycle=lifecycle_api::validate_candidate_cas_pr_transition(&cas,lifecycle).map_err(error)?;let gate=lifecycle_api::validate_gate_verdict(gate).map_err(error)?;
    if gate["gate_id"]!="G3"||gate["verdict"]!="pass"{return Err(failure("GitHub mutation requires a passing G3 PR identity/CAS verdict","materialize_the_exact_candidate_permission_and_cas_evidence"));}
    let mut chain=upstream.to_vec();chain.push(gate);let chain=lifecycle_api::validate_gate_chain(&chain,Some(&["G1","G2","G3"]),true).map_err(error)?;let gate=&chain[2];let identity=lifecycle_api::binding_identity(&lifecycle["binding"]).map_err(error)?;
    if lifecycle_api::binding_identity(&gate["binding"]).map_err(error)?!=identity||!gate["ordered_input_evidence_refs"].as_array().is_some_and(|values|values.contains(&cas["binding"]["evidence_ref"])){return Err(failure("G3 evidence does not bind selected PR lifecycle","create_a_successor_lifecycle_for_the_changed_identity"));}Ok((lifecycle,gate.clone()))
}
pub fn authoritative_publication_readback(runner:&mut impl Runner,root:&Path,repo:&str,selector:&str,cas:&Value,lifecycle:&Value)->Result<Value>{
    let readback=pull_request_readback(runner,root,repo,selector)?;let lifecycle=lifecycle_with_pr_readback(lifecycle,&readback)?;
    let receipt=crate::update_lifecycle_contract::materialize_publication_readback_receipt(cas,&lifecycle,&readback).map_err(|error|failure(error.to_string(),"read_back_the_exact_publication_identity"))?;
    Ok(json!({"pull_request_lifecycle":lifecycle,"authoritative_pr_readback":readback,"publication_readback_receipt":receipt}))
}
fn perform_checks(options:&Options,runner:&mut impl Runner,verification:&RemoteVerification,branch:&str)->Result<Value>{
    let selector=options.pr.as_deref().filter(|value|!value.is_empty()).unwrap_or(branch);let command=strings(&["gh","pr","checks",selector,"--repo",&verification.repo,if options.watch{"--watch"}else{"--watch=false"}]);let output=runner.execute(&options.root,&command).map_err(|error|failure(error.to_string(),"fix_gh_pr_checks_auth_or_wait_for_github_checks"))?;
    if ![0,8].contains(&output.returncode){let details=[output.stderr.trim(),output.stdout.trim()].into_iter().filter(|value|!value.is_empty()).collect::<Vec<_>>().join("\n");return Err(failure(format!("command failed ({}): {}\n{}",output.returncode,command.join(" "),details.chars().take(4000).collect::<String>()),"fix_gh_pr_checks_auth_or_wait_for_github_checks"));}
    let mut summary=base_summary(options,verification,branch);summary.as_object_mut().expect("summary object").extend(json!({"action":"checks","status":if output.returncode==8{"pending"}else{"ok"},"pr_selector":selector,"command":command,"checks_stdout":output.stdout.trim()}).as_object().expect("checks summary").clone());if output.returncode==8{summary["next_action"]=json!("wait_for_github_checks_or_rerun_with_--watch");}Ok(summary)
}
fn run_operation(options:&Options,runner:&mut impl Runner)->Result<Value>{
    let branch=match options.branch.as_deref().filter(|value|!value.is_empty()){Some(branch)=>branch.to_owned(),None=>{let value=run_command(runner,&options.root,strings(&["git","branch","--show-current"]),"checkout_a_named_branch_before_publication")?.stdout.trim().to_owned();if value.is_empty(){return Err(failure("current branch is detached","checkout_a_named_branch_before_publication"));}value}};
    let verification=verify_remote(runner,&options.root,options.repo.as_deref(),&options.remote)?;
    match options.action.as_str(){"push"=>perform_push(options,runner,&verification,&branch,None),"pr"=>{let lifecycle=build_lifecycle(options,runner,&verification,&branch)?;perform_pr(options,runner,&verification,&branch,&lifecycle)},"publish-pr"=>{let lifecycle=build_lifecycle(options,runner,&verification,&branch)?;let push=perform_push(options,runner,&verification,&branch,Some(&lifecycle))?;let mut summary=perform_pr(options,runner,&verification,&branch,&lifecycle).map_err(|mut error|{let mut partial=error.partial_success.take().unwrap_or_else(||json!({}));for key in ["user_task","remote_verified","repo","remote","branch","permission_state","permission_evidence_id","local_commit_sha","local_tree_sha","remote_readback_sha","remote_readback_ref"]{if let Some(value)=push.get(key){partial[key]=value.clone();}}partial["action"]=json!("publish-pr");partial["push"]=push.clone();partial["recovery_mode"]=json!("readback_only");error.partial_success=Some(partial);error})?;summary["action"]=json!("publish-pr");summary["push"]=push;Ok(summary)},"checks"=>perform_checks(options,runner,&verification,&branch),_=>Err(failure("unknown publication action","choose_push_pr_publish-pr_or_checks"))}
}
const SUMMARY_KEYS:&[&str]=&["status","action","user_task","remote_verified","repo","remote","branch","publication_boundary","permission_state","permission_evidence_id","worktree_dirty","local_commit_sha","local_tree_sha","remote_readback_sha","remote_readback_ref","mutation_completed","mutation_action","pr_number","pr_url","pr_selector","expected_pr_head_ref","expected_pr_head_sha","expected_pr_base_ref","expected_pr_base_sha","recovery_mode","next_action","verified_remote_policy"];
fn write_summary(path:&Path,summary:&Value)->Result<()>{
    let parent=std::env::var("AGENT_CANON_PARENT_ROOT").ok().map(|value|crate::python_text::python_strip(&value).to_owned()).filter(|value|!value.is_empty()).map(PathBuf::from);
    write_summary_with_parent(path,summary,parent.as_deref())
}
fn write_summary_with_parent(path:&Path,summary:&Value,parent:Option<&Path>)->Result<()>{
    use crate::authority::{AttestationRequest,ParentRootAttestor,Nonce128,NonEmptyTrimmedString};
    let parent=parent.ok_or_else(||failure("github-publication-staging: explicit parent root is required","select_the_explicit_parent_root_before_publication_staging"))?.canonicalize().map_err(|error|failure(error.to_string(),"select_the_explicit_parent_root_before_publication_staging"))?;
    let purpose=NonEmptyTrimmedString::new("github-publication-staging").map_err(|error|failure(error.to_string(),"select_the_explicit_parent_root_before_publication_staging"))?;
    let request=AttestationRequest{cwd:parent.clone(),explicit_root:Some(parent),source_root:None,clone_root:None,topic_marker:None,gitmodules:None,owner_evidence:None,expected_remote:None,expected_module_digest:None,child_handoff_token:None,purpose:purpose.clone(),nonce:Nonce128::generate().map_err(|error|failure(error.to_string(),"select_the_explicit_parent_root_before_publication_staging"))?};
    let attested=ParentRootAttestor::new().attest(&request).map_err(|error|failure(error.to_string(),"select_the_explicit_parent_root_before_publication_staging"))?;let value=crate::python_json::parse_json(&summary.to_string()).map_err(|error|failure(error,"materialize_publication_summary"))?;let mut bytes=crate::python_json::python_json_pretty_ascii_bytes(&value).map_err(|error|failure(error,"materialize_publication_summary"))?;bytes.push(b'\n');attested.write_parent_owned_file(path,&bytes,purpose).map_err(|error|failure(error.to_string(),"materialize_publication_summary"))?;Ok(())
}
fn emit_summary(options:&Options,summary:&Value)->Result<()>{
    for key in SUMMARY_KEYS{if let Some(value)=summary.get(*key){let value=match value{Value::Bool(value)=>if *value{"yes"}else{"no"}.into(),Value::String(value)=>value.clone(),Value::Null=>"None".into(),_=>value.to_string()};println!("{}={value}",key.to_uppercase());}}
    if let Some(path)=&options.summary{write_summary(path,summary)?;}Ok(())
}
pub fn run_with_runner(args:&[String],runner:&mut impl Runner)->i32{
    let options=match parse_options(args){Ok(Parsed::Help)=>{println!("{HELP}");return 0;},Ok(Parsed::Run(mut options))=>{options.root=match crate::path_resolution::resolve_non_strict(&options.root){Ok(root)=>root,Err(error)=>{eprintln!("{error}");return 1;}};options},Err(error)=>{eprintln!("{error}");return 2;}};
    let result=run_operation(&options,runner);let summary=match result{Ok(summary)=>summary,Err(error)=>{let mut summary=json!({"status":"fail","user_task":options.user_task,"remote_verified":false,"error":error.message.chars().take(4000).collect::<String>(),"next_action":error.next_action,"verified_remote_policy":"gh_verified_remote_required"});if let Some(partial)=error.partial_success{summary.as_object_mut().expect("summary object").extend(partial.as_object().cloned().unwrap_or_default());}eprintln!("{}",error.message.chars().take(4000).collect::<String>());if let Err(error)=emit_summary(&options,&summary){eprintln!("{}",error.message);}return 1;}};
    match emit_summary(&options,&summary){Ok(())=>0,Err(error)=>{eprintln!("{}",error.message);1}}
}
pub fn run(args:&[String])->i32{run_with_runner(args,&mut SystemRunner)}

#[cfg(test)]
mod tests {
    use super::*;
    const A:&str="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const B:&str="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const C:&str="cccccccccccccccccccccccccccccccccccccccc";
    const D:&str="dddddddddddddddddddddddddddddddddddddddd";
    const F:&str="ffffffffffffffffffffffffffffffffffffffff";
    const M:&str="1111111111111111111111111111111111111111";
    const T:&str="2222222222222222222222222222222222222222";
    struct Fake {mode:&'static str,calls:Vec<Vec<String>>,head_reads:usize}
    impl Fake {
        fn new(mode:&'static str)->Self{Self{mode,calls:Vec::new(),head_reads:0}}
        fn mutations(&self)->Vec<&Vec<String>>{self.calls.iter().filter(|args|args.first().map(String::as_str)==Some("git")&&args.get(1).map(String::as_str)==Some("push")||args.first().map(String::as_str)==Some("gh")&&args.get(1).map(String::as_str)==Some("pr")&&matches!(args.get(2).map(String::as_str),Some("create"|"edit"))).collect()}
    }
    impl Runner for Fake {
        fn execute(&mut self,_:&Path,args:&[String])->std::io::Result<CommandResult>{
            self.calls.push(args.into());let mut code=0;let mut stderr=String::new();let stdout=match args.first().map(String::as_str){
                Some("git")=>match args.get(1).map(String::as_str){
                    Some("branch")=>"topic\n".into(),Some("remote")=>if self.mode=="https"{"https://github.com/owner/repo.git\n".into()}else{format!("git@github.com:{}.git\n",if self.mode=="repo-mismatch"{"other/wrong"}else if self.mode=="fork"{"forker/repo"}else{"owner/repo"})},Some("status")=>String::new(),
                    Some("rev-parse")=>{let revision=args.get(2).map(String::as_str).unwrap_or("");let result=match revision{"origin/main"=>C,"HEAD^{tree}"=>B,"HEAD"=>{self.head_reads+=1;if self.mode=="local-drift"&&self.head_reads>1{F}else{A}},value if value==format!("{A}^{{tree}}")=>B,value if value==format!("{C}^{{tree}}")=>D,_=>A};format!("{result}\n")},
                    Some("push")=>String::new(),Some("ls-remote")=>format!("{}\trefs/heads/topic\n",if self.mode=="remote-mismatch"{F}else{A}),_=>panic!("unexpected git argv: {args:?}"),
                },
                Some("gh")=>match (args.get(1).map(String::as_str),args.get(2).map(String::as_str)){
                    (Some("repo"),Some("view"))=>{let fork=args.iter().any(|arg|arg=="forker/repo"||arg=="other/wrong");if fork{json!({"nameWithOwner":if self.mode=="fork"{"forker/repo"}else{"other/wrong"},"viewerPermission":"WRITE","parent":{"nameWithOwner":if self.mode=="fork"{"owner/repo"}else{"other/base"}}}).to_string()}else{json!({"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo","sshUrl":"git@github.com:owner/repo.git","viewerPermission":if self.mode=="permission-unknown"{Value::Null}else{json!("WRITE")}}).to_string()}},
                    (Some("api"),Some("user"))=>json!({"id":7,"login":"actor","name":"Actor"}).to_string(),
                    (Some("pr"),Some("checks"))=>{code=8;"pending\n".into()},
                    (Some("pr"),Some("list"))=>if ["existing","update","reviews","merged"].contains(&self.mode){json!([{"number":23,"url":"https://github.com/owner/repo/pull/23","headRefName":"topic","baseRefName":"main"}]).to_string()}else{"[]".into()},
                    (Some("pr"),Some("create"))=>{if self.mode=="create-fails"{code=1;stderr="HTTP403".into();} "https://github.com/owner/repo/pull/23\n".into()},
                    (Some("pr"),Some("edit"))=>"updated\n".into(),
                    (Some("pr"),Some("view"))=>json!({"number":23,"url":"https://github.com/owner/repo/pull/23","state":if self.mode=="merged"{"MERGED"}else{"OPEN"},"isDraft":false,"baseRefName":"main","headRefName":"topic","headRefOid":A,"headRepository":{"nameWithOwner":if self.mode=="fork"{"forker/repo"}else{"owner/repo"}},"reviewDecision":if self.mode=="reviews"{"CHANGES_REQUESTED"}else{"APPROVED"},"reviews":if self.mode=="reviews"{json!([{"id":"review-1","author":{"login":"reviewer"},"state":"CHANGES_REQUESTED","body":"fix"}])}else{json!([])},"mergeCommit":if self.mode=="merged"{json!({"oid":M})}else{Value::Null}}).to_string(),
                    (Some("api"),Some(endpoint)) if endpoint.contains("/pulls/23")=>{if self.mode=="readback-fails"{code=1;stderr="readback unavailable".into();}"".into()+&json!({"number":23,"url":"https://github.com/owner/repo/pull/23","state":if self.mode=="merged"{"closed"}else{"open"},"isDraft":false,"merged":self.mode=="merged","mergeCommitOid":if self.mode=="merged"{json!(M)}else{Value::Null},"baseRefName":"main","baseRefOid":C,"headRefName":"topic","headRefOid":if self.mode=="api-head-mismatch"{F}else{A},"headRepository":if self.mode=="fork"{"forker/repo"}else{"owner/repo"}}).to_string()},
                    (Some("api"),Some(endpoint)) if endpoint==format!("repos/owner/repo/git/commits/{M}")=>json!({"commit_sha":M,"tree_sha":T,"parents":[C]}).to_string(),
                    (Some("api"),Some(endpoint)) if endpoint==format!("repos/owner/repo/git/commits/{C}")=>json!({"commit_sha":C,"tree_sha":D}).to_string(),
                    (Some("api"),Some(endpoint)) if endpoint=="repos/owner/repo/commits/main"=>json!({"commit_sha":C,"tree_sha":D}).to_string(),
                    _=>panic!("unexpected gh argv: {args:?}"),
                },_=>panic!("unexpected program: {args:?}"),
            };Ok(CommandResult{args:args.into(),returncode:code,stdout,stderr})
        }
    }
    fn fixture(action:&str)->(tempfile::TempDir,Options){
        let directory=tempfile::tempdir_in(std::env::temp_dir().canonicalize().expect("canonical temporary parent")).expect("publication fixture");let body=directory.path().join("body.md");std::fs::write(&body,"## Problem\nKeep the qualified publication identity.\n").expect("body input");let options=Options{root:directory.path().into(),action:action.into(),user_task:Some("publish qualified topic".into()),repo:Some("owner/repo".into()),remote:"origin".into(),base:"main".into(),title:Some("Qualified change".into()),body:Some(body),..Options::default()};(directory,options)
    }
    #[test]
    fn option_prefixes_are_scoped_and_visible_task_is_required(){
        assert!(parse_options(&strings(&["push"])).is_err());let parsed=parse_options(&strings(&["--r=.","push","--user-t","publish","--rem","origin"])).expect("unique prefixes");let Parsed::Run(options)=parsed else{panic!("run options expected")};assert_eq!(options.remote,"origin");assert!(parse_options(&strings(&["push","--user-task","publish","--re","repo"])).is_err());
    }
    #[test]
    fn normalized_remote_forms_preserve_the_public_slug(){for remote in ["git@github.com:owner/repo.git","git@github.com:owner/repo.git/","https://github.com/owner/repo.git","ssh://git@github.com/owner/repo.git","owner/repo"]{assert_eq!(normalized_repo_slug(remote).as_deref(),Some("owner/repo"),"{remote}");}assert_eq!(normalized_repo_slug(""),None);}
    #[test]
    fn push_uses_exact_nonforced_ref_and_checks_after_identity(){for mode in ["ok","https"]{let (_directory,options)=fixture("push");let mut runner=Fake::new(mode);let summary=run_operation(&options,&mut runner).expect("verified push");assert_eq!(summary["remote_readback_sha"],A);let mutations=runner.mutations();assert_eq!(mutations.len(),1);assert_eq!(mutations[0],&strings(&["git","push","-u","origin",&format!("{A}:refs/heads/topic")]));assert_eq!(summary["local_identity_before_push"],summary["local_identity_after_push"]);}}
    #[test]
    fn mismatched_repository_branch_remote_or_local_identity_never_force_pushes(){
        for mode in ["repo-mismatch","remote-mismatch","local-drift","branch-mismatch"]{let (_directory,mut options)=fixture("push");if mode=="branch-mismatch"{options.branch=Some("other".into());}let mut runner=Fake::new(mode);assert!(run_operation(&options,&mut runner).is_err(),"{mode}");assert!(runner.calls.iter().all(|args|!args.iter().any(|arg|arg=="--force"||arg=="--force-with-lease")));assert!(runner.mutations().len()<=1);if ["repo-mismatch","branch-mismatch"].contains(&mode){assert!(runner.mutations().is_empty());}}
    }
    #[test]
    fn missing_body_and_unknown_permission_stop_before_mutation(){for mode in ["missing-body","permission-unknown"]{let (_directory,mut options)=fixture("publish-pr");if mode=="missing-body"{options.body=Some(options.root.join("missing.md"));}let mut runner=Fake::new(mode);assert!(run_operation(&options,&mut runner).is_err());assert!(runner.mutations().is_empty());}}
    #[test]
    fn create_existing_update_and_fork_routes_keep_verified_lifecycle(){
        for mode in ["ok","existing","update","fork"]{let (_directory,mut options)=fixture("pr");options.update=mode=="update";let mut runner=Fake::new(mode);let summary=run_operation(&options,&mut runner).expect("PR operation");assert_eq!(summary["pr_number"],23);assert_eq!(summary["pull_request_lifecycle"]["state"],"ready");assert_eq!(summary["action"],if mode=="existing"{"pr-existing"}else if mode=="update"{"pr-update"}else{"pr-create"});assert_eq!(runner.mutations().len(),usize::from(mode!="existing"));if mode=="fork"{assert_eq!(summary["pull_request_lifecycle"]["kind"],"fork");}}
    }
    #[test]
    fn failed_pr_readback_keeps_one_completed_mutation_and_readback_only_recovery(){let (_directory,options)=fixture("pr");let mut runner=Fake::new("readback-fails");let error=run_operation(&options,&mut runner).expect_err("readback must fail");let partial=error.partial_success.expect("completed mutation evidence");assert_eq!(partial["mutation_completed"],true);assert_eq!(partial["pr_number"],23);assert_eq!(partial["recovery_mode"],"readback_only");assert_eq!(runner.mutations().len(),1);}
    #[test]
    fn publish_pr_retains_pushed_identity_when_creation_fails(){let (_directory,options)=fixture("publish-pr");let mut runner=Fake::new("create-fails");let error=run_operation(&options,&mut runner).expect_err("create failure");let partial=error.partial_success.expect("push evidence");assert_eq!(partial["push"]["status"],"ok");assert_eq!(partial["remote_readback_sha"],A);assert_eq!(partial["recovery_mode"],"readback_only");assert_eq!(runner.mutations().len(),2);}
    #[test]
    fn two_independent_pr_snapshots_reject_a_changed_head(){let mut runner=Fake::new("api-head-mismatch");assert!(pull_request_readback(&mut runner,Path::new("."),"owner/repo","23").is_err());assert!(runner.mutations().is_empty());assert_eq!(runner.calls.len(),2);}
    #[test]
    fn external_reviews_keep_essence_and_merged_readback_keeps_cas_tree(){
        for mode in ["reviews","merged"]{let (_directory,options)=fixture("pr");let mut runner=Fake::new(mode);let summary=run_operation(&options,&mut runner).expect("retained review/merge identity");let lifecycle=&summary["pull_request_lifecycle"];assert_eq!(lifecycle["pr_essence"]["problem"],"publish qualified topic");if mode=="reviews"{assert_eq!(lifecycle["state"],"changes_requested");assert_eq!(lifecycle["reviews"][0]["reviewer_id"],"reviewer");assert_eq!(lifecycle["reviews"][0]["body_digest"],format!("sha256:{:x}",Sha256::digest(br#""fix""#)));}else{assert_eq!(lifecycle["state"],"merged");assert!(runner.calls.iter().any(|args|args.iter().any(|value|value==&format!("repos/owner/repo/git/commits/{M}"))));}}
    }
    #[test]
    fn pending_checks_are_read_only_success(){let (_directory,options)=fixture("checks");let mut runner=Fake::new("ok");let summary=run_operation(&options,&mut runner).expect("pending checks");assert_eq!(summary["status"],"pending");assert!(runner.mutations().is_empty());}
    #[test]
    fn explicit_parent_is_required_before_summary_file_creation(){let root=tempfile::tempdir().expect("output fixture");let output=root.path().join("external-summary.json");assert!(write_summary_with_parent(&output,&json!({}),None).is_err());assert!(!output.exists());assert_eq!(std::fs::read_dir(root.path()).expect("fixture entries").count(),0);}
    #[test]
    fn g3_reuses_captured_g1_g2_cas_inputs_and_rejects_unknown_permission(){
        let fixture:Value=serde_json::from_str(include_str!("../../../../../tests/fixtures/generated_completeness/github_g1_g2.json")).expect("captured inputs");
        for context in fixture["contexts"].as_array().expect("contexts"){
            let lifecycle=&context["lifecycle"];let cas=&context["candidate_cas_receipt"];let rebind=&context["source_main_rebind_receipt"];let upstream=context["gate_verdicts"].as_array().expect("upstream gates");let result=materialize_pr_identity_gate(Path::new(text(context,"source_root")),lifecycle,cas,rebind,upstream);
            if context["context"]=="permission_unknown"{assert!(result.is_err());continue;}let gate=result.expect("verified G3");assert_eq!(gate["gate_id"],"G3");assert_eq!(gate["verdict"],"pass");assert_eq!(gate["ordered_input_evidence_refs"].as_array().expect("gate inputs").len(),4);let checked=require_pr_identity_gate(lifecycle,cas,rebind,upstream,&gate).expect("exact G3 consumption");assert_eq!(&checked.0,lifecycle);assert_eq!(checked.1,gate);
            let mut changed=cas.clone();changed["binding"]["candidate_sha"]=json!(F);assert!(materialize_pr_identity_gate(Path::new("/oracle"),lifecycle,&changed,rebind,upstream).is_err());
        }
    }
}
