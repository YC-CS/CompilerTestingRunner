import os
import shutil
import zipfile

from utils import *
from StateEnum import State
from StateEnum import state_to_str

# 1 for csmith   2 for yarpgen
generator = 2

# 1 for C   2 for Cpp
language = 2

# Absolute path recommended
GENERATOR_ELF = '/home/workspace/yarpgen-pro/build/yarpgen'
TEST_FOLDER = '/home/workspace/testing/'

# This root is only filled if you are using Csmith
CSMITH_LIB_ROOT = '/home/workspace/CompilerTestingRunner/lib/'


GENERATOR_OUTPUT_ROOT = TEST_FOLDER + 'cases/'
BACKUP_FOLDER = TEST_FOLDER + 'backup/'
LOG_FOLDER = TEST_FOLDER + 'log/'

if not os.path.exists(TEST_FOLDER):
    os.makedirs(TEST_FOLDER)

if not os.path.exists(GENERATOR_OUTPUT_ROOT):
    os.makedirs(GENERATOR_OUTPUT_ROOT)

if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)

if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)



TIME_STR = get_current_time_str()

def csmith_runner(test_num: int = 1):

    global GENERATOR_ELF, GENERATOR_OUTPUT_ROOT

    for i in range(test_num):
        output_file = GENERATOR_OUTPUT_ROOT + TIME_STR + '--' + str(i) + '.c'
        cmd = GENERATOR_ELF + " -o " + output_file
        cmd_list = cmd.split(' ')
        ret, stdout, stderr = run_cmd(command=cmd_list, working_dir=GENERATOR_OUTPUT_ROOT, timeout=10)
        if ret != 0:
            print("CSMITH Error: {}".format(cmd))


def yarpgen_runner(test_num: int = 1):

    global GENERATOR_ELF , GENERATOR_OUTPUT_ROOT

    for i in range(test_num):
        os.system( GENERATOR_ELF + ' -o ' + GENERATOR_OUTPUT_ROOT )


def generator_runner(test_num: int = 1):

    global GENERATOR_ELF, GENERATOR_OUTPUT_ROOT

    if not os.path.exists(GENERATOR_ELF):
        raise ValueError('You must have a legal generator elf')

    if not os.path.exists(GENERATOR_OUTPUT_ROOT):
        raise ValueError('You should have a legal generator output root')

    if generator == 1:
        csmith_runner(test_num)
    elif generator == 2:
        yarpgen_runner(test_num)
    else :
        raise ValueError('You should choose a supported generator')

    # for case_file in os.listdir(GENERATOR_OUTPUT_ROOT):
    #     if not (case_file.endswith('.c') or case_file.endswith('.cpp')):
    #         continue
    #
    #     case_path = GENERATOR_OUTPUT_ROOT + case_file
    #
    #     size = os.path.getsize(case_path)
    #     size_lim = 51200
    #
    #     if size > size_lim:
    #         print(case_file + ' oversize')
    #         os.remove(case_path)


def compile_elf(compile_cmd: str):
    global GENERATOR_OUTPUT_ROOT

    try:
        print("COMPILE: " + compile_cmd)
        ret, _, _ = run_cmd(compile_cmd.split(' '), GENERATOR_OUTPUT_ROOT, 30)
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
        time_budget = 30
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


def process_compiler(compilers: list, options: list):
    global GENERATOR_OUTPUT_ROOT , LOG_FOLDER

    # for each test case
    for case_file in os.listdir(GENERATOR_OUTPUT_ROOT):
        if not (case_file.endswith('.c') or case_file.endswith('.cpp')):
            continue
        execution_res = {}
        compilation_timeout_files = {}
        execution_timeout_files = {}
        compiler_internal_error = {}
        compiler_opt_error = {}
        tail = TIME_STR + '.txt'

        checksum_array = []
        diff_file = LOG_FOLDER + case_file + '.diff'

        for compiler in compilers:
            cie_file = LOG_FOLDER + compiler + '-cie-' + tail  # compiler_internal_error
            ct_file = LOG_FOLDER + compiler + '-ct-' + tail  # compiler_timeout
            coe_file = LOG_FOLDER + compiler + '-coe-' + tail  # compiler_opt_error
            et_file = LOG_FOLDER + compiler + '-et-' + tail  # execution_timeout
            er_file = LOG_FOLDER + compiler + '-er-' + tail  # execution_res

            for opt in options:
                elf_name = case_name_to_elf_name(compiler, case_file, opt)
                if generator == 1:
                    compile_cmd = compiler + ' -I ' + CSMITH_LIB_ROOT + ' -' + opt + ' ' + case_file + ' -o ' + elf_name
                elif generator == 2:
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
                    checksum_array.append(ret_val)

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

        # compare all checksum
        print("comparing checksum from:{}\n".format(case_file))
            # if the checksums are not all same
        if len(set(checksum_array)) != 1:
            print("find checksum difference in {}".format(case_file))
            for checksum in checksum_array:
                write_file(str(checksum) , diff_file)
            backup_file(case_file)



def compile_and_execute():
    if language == 1:
        compilers = ['clang', 'gcc']
    elif language == 2:
        compilers = ['clang++', 'g++']
    else :
        raise ValueError('You should choose a supported language')

    options = []
    for level in range(0, 4):
        options.append('O' + str(level))

    process_compiler(compilers, options)


def move_and_zip():
    global GENERATOR_OUTPUT_ROOT , TEST_FOLDER , BACKUP_FOLDER , LOG_FOLDER

    zip_dir = TEST_FOLDER + 'Testing-' + TIME_STR
    os.makedirs(zip_dir)

    for ELF_file in os.listdir(GENERATOR_OUTPUT_ROOT):
        ELF_path = GENERATOR_OUTPUT_ROOT + ELF_file
        if 'ELF' in ELF_file :
            os.remove(ELF_path)
            continue

    shutil.move(GENERATOR_OUTPUT_ROOT, zip_dir)
    shutil.move(BACKUP_FOLDER, zip_dir)
    shutil.move(LOG_FOLDER, zip_dir)
    print('backup done')

    zip_file = zip_dir + '.zip'
    zip = zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED)
    for item in os.listdir(zip_dir):
        zip.write(zip_dir + os.sep + item , item)
    zip.close()
    print('zip done')



if __name__ == '__main__':
    generator_runner(10)
    compile_and_execute()
    move_and_zip()

