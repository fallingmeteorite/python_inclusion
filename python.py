use std::collections::HashSet;
use std::env;
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

// 日志级别枚举
#[derive(Debug, Clone, Copy, PartialEq)]
enum LogLevel {
    Debug,
    Info,
    Warning,
    Critical,
}

// 日志输出函数
fn log(level: LogLevel, message: &str) {
    match level {
        LogLevel::Debug => println!("\x1b[34m\x1b[107m | DEBUG : {}\x1b[0m", message),
        LogLevel::Info => println!("\x1b[32m\x1b[107m | INFO : {}\x1b[0m", message),
        LogLevel::Warning => println!("\x1b[33m\x1b[107m | WARNING : {}\x1b[0m", message),
        LogLevel::Critical => println!("\x1b[31m\x1b[103m | CRITICAL : {}\x1b[0m", message),
    }
}

// 从文件中读取包规则
fn read_package_rules(rule_file_path: &Path) -> io::Result<HashSet<String>> {
    let mut rules = HashSet::new();
    
    if rule_file_path.exists() {
        let file = File::open(rule_file_path)?;
        let reader = BufReader::new(file);
        
        for line in reader.lines() {
            let line = line?;
            let package_name = line.trim().to_string();
            if !package_name.is_empty() {
                rules.insert(package_name);
            }
        }
    }
    
    Ok(rules)
}

// 检测文件编码（简化版本）
fn detect_file_encoding_simple(data: &[u8]) -> &'static str {
    // 检查UTF-8 BOM
    if data.len() >= 3 && data[0..3] == [0xEF, 0xBB, 0xBF] {
        return "utf-8-sig";
    }
    
    // 尝试解码为UTF-8
    if std::str::from_utf8(data).is_ok() {
        return "utf-8";
    }
    
    // 默认返回本地编码（简化处理）
    "local"
}

// 读取文件并尝试解码
fn read_file_with_encoding(file_path: &Path) -> io::Result<String> {
    let mut file = File::open(file_path)?;
    let mut buffer = Vec::new();
    file.read_to_end(&mut buffer)?;
    
    let encoding = detect_file_encoding_simple(&buffer);
    
    match encoding {
        "utf-8" => {
            String::from_utf8(buffer)
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Invalid UTF-8"))
        }
        "utf-8-sig" => {
            // 去除BOM
            String::from_utf8(buffer[3..].to_vec())
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Invalid UTF-8"))
        }
        "local" => {
            // 对于非UTF-8编码，尝试使用系统本地编码
            // 这是一个简化处理，实际应该根据系统编码来处理
            Ok(String::from_utf8_lossy(&buffer).to_string())
        }
        _ => {
            String::from_utf8(buffer)
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "Invalid encoding"))
        }
    }
}

// 从requirements.txt中移除黑名单包
fn filter_requirements_file(file_path: &Path, blacklist: &HashSet<String>) -> io::Result<bool> {
    let mut modified = false;
    
    // 读取文件内容
    let content = read_file_with_encoding(file_path)?;
    let lines: Vec<&str> = content.lines().collect();
    let mut new_lines = Vec::new();
    
    for line in lines {
        let trimmed = line.trim();
        
        if trimmed.is_empty() {
            new_lines.push(line.to_string());
            continue;
        }
        
        // 检查注释行
        if trimmed.starts_with('#') {
            new_lines.push(line.to_string());
            continue;
        }
        
        // 提取包名（移除版本说明等）
        let package_name = if let Some(index) = trimmed.find(['=', '<', '>', '~', '!', '#', ' ', '\t']) {
            &trimmed[..index]
        } else {
            trimmed
        };
        
        let clean_package_name = package_name.trim().to_string();
        
        // 检查是否在黑名单中
        if blacklist.contains(&clean_package_name) {
            log(LogLevel::Warning, &format!(
                "The current command is detected to be making changes to the |{}| library, and the current command will be intercepted!",
                clean_package_name
            ));
            log(LogLevel::Warning, "If you confirm that the change is necessary, add the parameter |-rules_open| and set it to |off|");
            
            // 跳过这一行（不添加到新内容中）
            modified = true;
        } else {
            new_lines.push(line.to_string());
        }
    }
    
    // 如果文件被修改，写回
    if modified {
        let mut file = File::create(file_path)?;
        for line in &new_lines {
            writeln!(file, "{}", line)?;
        }
    }
    
    Ok(modified)
}

// 删除卸载缓存
fn delete_uninstall_cache(parent_path: &Path) -> io::Result<()> {
    let site_packages = parent_path.join("Lib").join("site-packages");
    
    if site_packages.exists() && site_packages.is_dir() {
        match fs::read_dir(&site_packages) {
            Ok(entries) => {
                for entry in entries {
                    if let Ok(entry) = entry {
                        let path = entry.path();
                        if let Some(file_name) = path.file_name() {
                            if let Some(name_str) = file_name.to_str() {
                                if name_str.starts_with('~') {
                                    let result = if path.is_dir() {
                                        fs::remove_dir_all(&path)
                                    } else {
                                        fs::remove_file(&path)
                                    };
                                    
                                    match result {
                                        Ok(_) => {
                                            log(LogLevel::Info, &format!("{} The folder has been deleted", path.display()));
                                        }
                                        Err(e) => {
                                            log(LogLevel::Warning, &format!("Failed to delete {}: {}", path.display(), e));
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Err(e) => {
                log(LogLevel::Warning, &format!("Failed to read site-packages directory: {}", e));
            }
        }
    }
    
    Ok(())
}

// 解析命令行参数
fn parse_args() -> (bool, bool, bool, Vec<String>) {
    let args: Vec<String> = env::args().skip(1).collect();
    let mut rules_open = true;
    let mut delete_cache = false;
    let mut debug_info = false;
    let mut pip_args = Vec::new();
    let mut i = 0;
    
    while i < args.len() {
        match args[i].as_str() {
            "-rules_open" => {
                if i + 1 < args.len() {
                    rules_open = args[i + 1].to_lowercase() == "true";
                    i += 1;
                }
            }
            "-delete_cache" => {
                if i + 1 < args.len() {
                    delete_cache = args[i + 1].to_lowercase() == "true";
                    i += 1;
                }
            }
            "-debugging_information" => {
                if i + 1 < args.len() {
                    debug_info = args[i + 1].to_lowercase() == "true";
                    i += 1;
                }
            }
            "-h" | "--help" => {
                println!("Usage: pip_wrapper [OPTIONS] [PIP_ARGS...]");
                println!();
                println!("Options:");
                println!("  -rules_open true|false      Whether or not to apply the rule (default: true)");
                println!("  -delete_cache true|false    Delete garbage from uninstalled packages (default: false)");
                println!("  -debugging_information true|false  Whether to output debug information (default: false)");
                println!("  -h, --help                  Show this help message");
                std::process::exit(0);
            }
            arg => {
                // 不是我们的选项，应该是pip参数
                pip_args.push(arg.to_string());
            }
        }
        i += 1;
    }
    
    (rules_open, delete_cache, debug_info, pip_args)
}

// 提取requirement文件
fn extract_requirement_files(args: &[String]) -> (Vec<String>, Vec<String>) {
    let mut requirement_files = Vec::new();
    let mut other_args = Vec::new();
    let mut i = 0;
    
    while i < args.len() {
        if args[i] == "-r" || args[i] == "--requirement" {
            if i + 1 < args.len() {
                requirement_files.push(args[i + 1].clone());
                i += 1; // 跳过文件名
            }
        } else {
            other_args.push(args[i].clone());
        }
        i += 1;
    }
    
    (requirement_files, other_args)
}

// 运行命令
fn run_command(
    pip_args: &[String],
    rules_open: bool,
    delete_cache: bool,
    parent_path: &Path,
    debug_info: bool,
) -> io::Result<()> {
    let mut should_run = true;
    
    // 提取requirement文件
    let (requirement_files, other_args) = extract_requirement_files(pip_args);
    
    // 构建命令字符串用于检查
    let command_str = other_args.join(" ");
    
    // 如果启用规则检测
    if rules_open {
        let rule_file_path = parent_path.join("Inclusion_rules_package.txt");
        let blacklist = match read_package_rules(&rule_file_path) {
            Ok(rules) => rules,
            Err(e) => {
                log(LogLevel::Warning, &format!("Failed to read rules file: {}", e));
                HashSet::new()
            }
        };
        
        // 检查命令中是否包含黑名单包
        for package in &blacklist {
            if command_str.contains(package) {
                // 检查是否是安装命令
                if command_str.contains("install") {
                    log(LogLevel::Warning, &format!(
                        "The current command is detected to be making changes to the |{}| library, and the current command will be intercepted!",
                        package
                    ));
                    log(LogLevel::Warning, "If you confirm that the change is necessary, add the parameter |-rules_open| and set it to |off|");
                    should_run = false;
                    break;
                }
            }
        }
        
        // 检查requirements.txt文件
        for req_file in &requirement_files {
            log(LogLevel::Info, "The current command is detected to be installing dependent files in batches, and requirements.txt files are being detected");
            log(LogLevel::Info, &format!("{} detects the file path", req_file));
            
            let req_path = Path::new(req_file);
            if req_path.exists() {
                if let Err(e) = filter_requirements_file(req_path, &blacklist) {
                    log(LogLevel::Warning, &format!("Failed to filter requirements file {}: {}", req_file, e));
                }
            }
        }
    }
    
    // 删除卸载缓存
    if delete_cache {
        if let Err(e) = delete_uninstall_cache(parent_path) {
            log(LogLevel::Warning, &format!("Failed to delete cache: {}", e));
        }
    }
    
    // 构建Python路径
    let python_path = parent_path.join("original_python.exe");
    
    if should_run {
        // 重新构建完整的参数列表
        let mut all_args = other_args.clone();
        for req_file in &requirement_files {
            all_args.push("-r".to_string());
            all_args.push(req_file.clone());
        }
        
        if debug_info {
            log(LogLevel::Debug, &format!("{} {}", python_path.display(), all_args.join(" ")));
        }
        
        // 执行命令
        let mut cmd = if cfg!(target_os = "windows") {
            let mut cmd = Command::new("powershell.exe");
            cmd.arg(python_path.to_string_lossy().to_string());
            cmd
        } else {
            Command::new(&python_path)
        };
        
        // 添加参数
        for arg in &all_args {
            cmd.arg(arg);
        }
        
        // 设置标准输入输出
        cmd.stdin(Stdio::inherit())
           .stdout(Stdio::inherit())
           .stderr(Stdio::inherit());
        
        match cmd.spawn() {
            Ok(mut child) => {
                if let Err(e) = child.wait() {
                    log(LogLevel::Critical, &format!("Failed to wait for command: {}", e));
                }
            }
            Err(e) => {
                log(LogLevel::Critical, &format!("Failed to execute command: {}", e));
            }
        }
    }
    
    Ok(())
}

fn main() -> io::Result<()> {
    // 解析命令行参数
    let (rules_open, delete_cache, debug_info, pip_args) = parse_args();
    
    // 获取当前程序路径
    let current_exe = env::current_exe()?;
    let execution_path = current_exe.parent()
        .unwrap_or_else(|| Path::new("."))
        .to_path_buf();
    
    // 运行命令
    if let Err(e) = run_command(&pip_args, rules_open, delete_cache, &execution_path, debug_info) {
        log(LogLevel::Critical, &format!("Error: {}", e));
        std::process::exit(1);
    }
    
    Ok(())
}
