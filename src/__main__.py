import os
import shutil

from utils import *
from StateEnum import State
from StateEnum import state_to_str

# 'csmith' or 'yarpgen'
generator = 'yarpgen'

# 'c' or 'cpp'
language = 'cpp'

# Absolute path recommended
GENERATOR_ELF = '/home/workspace/CompilerTestingRunner/yarpgen'
GENERATOR_OUTPUT_ROOT = '/home/workspace/cases/'
BACKUP_FOLDER = '/home/workspace/testing/backup/'
LOG_FOLDER = '/home/workspace/testing/log/'

# This line is only filled if you are using Csmith
CSMITH_LIB_ROOT = '/home/workspace/testing/lib/'


TIME_STR = get_current_time_str()

def csmith_runner(test_num: int = 1):

    global GENERATOR_ELF, GENERATOR_OUTPUT_ROOT

    if not os.path.exists(GENERATOR_ELF):
        raise ValueError('You must have a legal generator elf')

    if not os.path.exists(GENERATOR_OUTPUT_ROOT):
        raise ValueError('You should have a legal generator output root')

    for i in range(test_num):
        output_file = GENERATOR_OUTPUT_ROOT + TIME_STR + '--' + str(i) + '.c'
        cmd = GENERATOR_ELF + " -o " + output_file
        cmd_list = cmd.split(' ')
        ret, stdout, stderr = run_cmd(command=cmd_list, working_dir=GENERATOR_OUTPUT_ROOT, timeout=10)
        if ret != 0:
            print("CSMITH Error: {}".format(cmd))


def yarpgen_runner(test_num: int = 1):

    global GENERATOR_ELF , GENERATOR_OUTPUT_ROOT

    if not os.path.exists(GENERATOR_ELF):
        raise ValueError('You must have a legal generator elf')

    if not os.path.exists(GENERATOR_OUTPUT_ROOT):
        raise ValueError('You should have a legal generator output root')

    for i in range(test_num):
        os.system( GENERATOR_ELF + ' -o ' + GENERATOR_OUTPUT_ROOT )


def generator_runner(test_num: int = 1):

    if generator == 'csmith':
        csmith_runner(test_num)
    elif generator == 'yarpgen':
        yarpgen_runner(test_num)
    else :
        raise ValueError('You should choose a supported generator')

def compile_elf(compile_cmd: str):
    global GENERATOR_OUTPUT_ROOT

    try:
        print("COMPILE: " + compile_cmd)
        ret, _, _ = run_cmd(compile_cmd.split(' '), GENERATOR_OUTPUT_ROOT, 15)
    except subprocess.TimeoutExpired:
        print("COMPILER TIMEOUT: {}".format(compile_cmd))
        return State.COMPILE_TIMEOUT
    else:
        if ret != 0:
            print("COMPILER CRASH BY CMD: {}".format(compile_cmd))
            return State.COMPILE_CRASH
        else:
            return State.COMPILE_SUCC


def execute_elf(elf_name: str):
    global GENERATOR_OUTPUT_ROOT
    try:
        exe_cmd = './' + elf_name
        print("RUN TEST: " + exe_cmd)
        time_budget = 10
        ret, stdout, stderr = run_cmd([exe_cmd], GENERATOR_OUTPUT_ROOT, time_budget)
    except subprocess.TimeoutExpired:
        print("GENERATED DEAD-LOOP FILE: {}".format(elf_name))
        return State.EXECUTION_TIMEOUT, state_to_str(State.EXECUTION_TIMEOUT)

    if ret != 0:
        print("EXECUTABLE CRASH: {}".format(elf_name))
        return State.EXECUTION_CRASH, state_to_str(State.EXECUTION_CRASH)
    else:
        checksum = stdout[0]
        return State.EXECUTION_SUCC, checksum


def backup_file(case_name: str):
    global BACKUP_FOLDER, GENERATOR_OUTPUT_ROOT
    output = BACKUP_FOLDER + case_name
    if not os.path.exists(output):
        shutil.copyfile(GENERATOR_OUTPUT_ROOT + case_name, BACKUP_FOLDER + case_name)


def process_compiler(compiler: str, options: list):
    global GENERATOR_OUTPUT_ROOT , LOG_FOLDER
    execution_res = {}
    compilation_timeout_files = {}
    execution_timeout_files = {}
    compiler_internal_error = {}
    compiler_opt_error = {}
    tail = TIME_STR + '.txt'
    cie_file = LOG_FOLDER + compiler + '-cie-' + tail  # compiler_internal_error
    ct_file = LOG_FOLDER + compiler + '-ct-' + tail    # compiler_timeout
    coe_file = LOG_FOLDER + compiler + '-coe-' + tail  # compiler_opt_error
    et_file = LOG_FOLDER + compiler + '-et-' + tail    # execution_timeout
    er_file = LOG_FOLDER + compiler + '-er-' + tail    # execution_res

    # for each test case
    for case_file in os.listdir(GENERATOR_OUTPUT_ROOT):
        if not (case_file.endswith('.c') or case_file.endswith('.cpp')):
            continue
        for opt in options:
            elf_name = case_name_to_elf_name(compiler, case_file, opt)
            if generator == 'csmith':
                compile_cmd = compiler + ' -I ' + CSMITH_LIB_ROOT + ' -' + opt + ' ' + case_file + ' -o ' + elf_name
            elif generator == 'yarpgen':
                compile_cmd = compiler + ' -mcmodel=large -' + opt + ' ' + case_file + ' -o ' + elf_name
            compile_state = compile_elf(compile_cmd)
            if compile_state == State.COMPILE_TIMEOUT:
                write_file(compile_cmd + '\n', ct_file)
                insert_to_dict(case_file, compilation_timeout_files, elf_name)
                backup_file(case_file)
                continue
            elif compile_state == State.COMPILE_CRASH:
                insert_to_dict(case_file, compiler_internal_error, elf_name)
                write_file(compile_cmd + '\n', cie_file)
                backup_file(case_file)
                continue

            execute_state, ret_val = execute_elf(elf_name)
            # record all
            write_file(compile_cmd + ' -> ' + ret_val + '\n', er_file)
            # process state
            if execute_state == State.EXECUTION_SUCC:
                if case_file not in execution_res:
                    execution_res[case_file] = []
                elf_and_checksum = (elf_name, ret_val)
                # compare with timeout historical results
                if case_file in execution_timeout_files:
                    print("{} OPT ERROR {} AT {}, "
                          "both timeout and checksum are generated!".format(compiler, case_file, opt))
                    insert_to_dict(case_file, compiler_opt_error, elf_name)
                    write_file(compile_cmd + ' -> ' + ret_val + '\n', coe_file)
                    backup_file(case_file)
                # compare with historical results
                for (k, v) in execution_res[case_file]:
                    if ret_val != v:
                        print("{} OPT ERROR {} AT {}!".format(compiler, case_file, opt))
                        insert_to_dict(case_file, compiler_opt_error, elf_name)
                        write_file(compile_cmd + ' -> ' + ret_val + '\n', coe_file)
                        backup_file(case_file)
                execution_res[case_file].append(elf_and_checksum)

            elif execute_state == State.EXECUTION_TIMEOUT:
                insert_to_dict(case_file, execution_timeout_files, elf_name)
                write_file(compile_cmd + '\n', et_file)
                # compare with timeout historical results
                if case_file in execution_res:
                    print("{} OPT ERROR {} AT {}, "
                          "both timeout and checksum are generated!".format(compiler, case_file, opt))
                    insert_to_dict(case_file, compiler_opt_error, elf_name)
                    write_file(compile_cmd + ' -> EXECUTION_TIMEOUT\n', coe_file)
                    backup_file(case_file)
            elif execute_state == State.EXECUTION_CRASH:
                insert_to_dict(case_file, compiler_opt_error, elf_name)
                write_file(compile_cmd + ' -> EXECUTION_CRASH\n', coe_file)
                backup_file(case_file)

    return execution_res, execution_timeout_files


def merge_execution_res(execution_res: dict, options: list):
    same_execution_res = {}
    op_size = len(options)
    for c_file, res_list in execution_res.items():
        if len(res_list) == op_size:
            tmp_set = set(res_list)
            if len(tmp_set) == 1:
                same_execution_res[c_file] = res_list[0]
    return same_execution_res


def merge_execution_timeout_files(execution_timeout_files: dict, options: list):
    same_execution_timeout_files = {}
    op_size = len(options)
    for c_file, res_list in execution_timeout_files.items():
        if len(res_list) == op_size:  # all executable files are timeout
            same_execution_timeout_files[c_file] = state_to_str(State.EXECUTION_TIMEOUT)

    return same_execution_timeout_files


def compile_and_execute():
    if language == 'c':
        compilers = ['clang', 'gcc']
    elif language == 'cpp':
        compilers = ['clang++', 'g++']
    else :
        raise ValueError('You should choose a supported language')

    options = []
    for level in range(0, 4):
        options.append('O' + str(level))
    results = []
    for compiler in compilers:
        execution_res, execution_timeout_files = process_compiler(compiler, options)
        execution_res = merge_execution_res(execution_res, options)
        execution_timeout_files = merge_execution_timeout_files(execution_timeout_files, options)
        item = (compiler, execution_res, execution_timeout_files)
        results.append(item)

    compare_compiler_outputs(results)


def record_comparison_result(fname: str, name1: str, name2: str, dict1: dict, dict2: dict):
    global LOG_FOLDER
    diff_file = LOG_FOLDER + fname
    added, removed, modified, _ = dict_compare(dict1, dict2)
    if len(modified) != 0:
        write_file('MODIFIED: ' + name1 + ' ' + name2 + '\n' + str(modified), diff_file)
    if len(added) != 0:
        write_file('ADDED: ' + name1 + ' ' + name2 + '\n' + str(added), diff_file)
    if len(removed) != 0:
        write_file('REMOVED: ' + name1 + ' ' + name2 + '\n' + str(removed), diff_file)


def compare_compiler_outputs(results: list):
    end = len(results)
    for i in range(end):
        curr_item = results[i]
        curr_compiler = curr_item[0]
        curr_compiler_res = curr_item[1]
        curr_execution_timeout_files = curr_item[2]
        for j in range(i + 1, end):
            next_item = results[j]
            next_compiler = next_item[0]
            print('COMPARING ' + curr_compiler + ' ' + next_compiler)
            # dict2
            next_compiler_res = next_item[1]
            record_comparison_result('checksum-' + TIME_STR + '.diff', curr_compiler, next_compiler,
                                     curr_compiler_res, next_compiler_res)
            next_execution_timeout_files = next_item[2]
            record_comparison_result('timeout-' + TIME_STR + '.diff', curr_compiler, next_compiler,
                                     curr_execution_timeout_files, next_execution_timeout_files)


if __name__ == '__main__':
    generator_runner(1)
    compile_and_execute()

