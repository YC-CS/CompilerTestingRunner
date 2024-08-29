import os
import shutil
import zipfile

from utils import *
from StateEnum import State
from StateEnum import state_to_str
from StateEnum import Generator


# 此处设置代码生成器的种类，目前支持csmith和yarpgen
generator = Generator.yarpgen

# 代码生成器的可执行文件路径
GENERATOR_ELF = '/home/workspace/yarpgen-pro/build/yarpgen'

# 测试路径
TEST_FOLDER = '/home/workspace/testing/'

# Csmith库的路径
CSMITH_LIB_ROOT = '/home/workspace/CompilerTestingRunner/lib/'


GENERATOR_OUTPUT_FOLDER = TEST_FOLDER + 'cases/'
BACKUP_FOLDER = TEST_FOLDER + 'backup/'
LOG_FOLDER = TEST_FOLDER + 'log/'

if not os.path.exists(TEST_FOLDER):
    os.makedirs(TEST_FOLDER)

if not os.path.exists(GENERATOR_OUTPUT_FOLDER):
    os.makedirs(GENERATOR_OUTPUT_FOLDER)

if not os.path.exists(BACKUP_FOLDER):
    os.makedirs(BACKUP_FOLDER)

if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)


TIME_STR = get_current_time_str()

def generator_runner(test_num: int = 1):

    global GENERATOR_ELF, GENERATOR_OUTPUT_FOLDER

    if not os.path.exists(GENERATOR_ELF):
        raise ValueError('You must have a legal generator elf')

    if not os.path.exists(GENERATOR_OUTPUT_FOLDER):
        raise ValueError('You should have a legal generator output root')

    if generator == Generator.csmith:
        for i in range(test_num):
            output_file = GENERATOR_OUTPUT_FOLDER + TIME_STR + '--' + str(i) + '.c'
            print("generating " + output_file)
            cmd = GENERATOR_ELF + " -o " + output_file
            os.system(cmd)
    elif generator == Generator.yarpgen:
        for i in range(test_num):
            os.system(GENERATOR_ELF + ' -o ' + GENERATOR_OUTPUT_FOLDER)
    else :
        raise ValueError('You should choose a supported generator')

def compile_elf(compile_cmd: str):
    global GENERATOR_OUTPUT_FOLDER

    try:
        print("COMPILE: " + compile_cmd)
        ret, _, _ = run_cmd(compile_cmd.split(' '), GENERATOR_OUTPUT_FOLDER, 30)
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
    global GENERATOR_OUTPUT_FOLDER
    try:
        exe_cmd = './' + elf_name
        print("RUN TEST: " + exe_cmd)
        ret, stdout, stderr = run_cmd([exe_cmd], GENERATOR_OUTPUT_FOLDER, 30)
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
    global BACKUP_FOLDER, GENERATOR_OUTPUT_FOLDER
    output = BACKUP_FOLDER + case_name
    if not os.path.exists(output):
        shutil.copyfile(GENERATOR_OUTPUT_FOLDER + case_name, BACKUP_FOLDER + case_name)


def process_compiler(compilers: list, options: list):
    global GENERATOR_OUTPUT_FOLDER , LOG_FOLDER

    # for each test case
    for case_file in os.listdir(GENERATOR_OUTPUT_FOLDER):
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
                if generator == Generator.csmith:
                    compile_cmd = compiler + ' -I ' + CSMITH_LIB_ROOT + ' -' + opt + ' ' + case_file + ' -o ' + elf_name
                elif generator == Generator.yarpgen:
                    compile_cmd = compiler + ' -' + opt + ' ' + case_file + ' -o ' + elf_name

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
        if len(checksum_array) != 0:
            if len(set(checksum_array)) != 1:
                print("find checksum difference in {}".format(case_file))
                for checksum in checksum_array:
                    write_file(str(checksum), diff_file)
                backup_file(case_file)



def compile_and_execute():
    if generator == Generator.csmith:
        compilers = ['clang', 'gcc']
    elif generator == Generator.yarpgen:
        compilers = ['clang++', 'g++']
    else :
        raise ValueError('You should choose a supported generator')

    options = []
    for level in range(0, 4):
        options.append('O' + str(level))

    process_compiler(compilers, options)


def move_and_compress():
    global GENERATOR_OUTPUT_FOLDER , TEST_FOLDER , BACKUP_FOLDER , LOG_FOLDER

    testing_dir = TEST_FOLDER + 'Testing-' + TIME_STR
    os.makedirs(testing_dir)

    for ELF_file in os.listdir(GENERATOR_OUTPUT_FOLDER):
        ELF_path = GENERATOR_OUTPUT_FOLDER + ELF_file
        if 'ELF' in ELF_file :
            os.remove(ELF_path)
            continue

    shutil.move(GENERATOR_OUTPUT_FOLDER, testing_dir)
    shutil.move(BACKUP_FOLDER, testing_dir)
    shutil.move(LOG_FOLDER, testing_dir)
    print('backup done')

    zip_name = testing_dir + ".zip"
    zip = zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED)

    for root, dirs, files in os.walk(testing_dir):
        for file in files:
            # 构建文件的完整路径
            file_path = os.path.join(root, file)
            # 将文件写入ZIP文件
            zip.write(file_path, os.path.relpath(file_path, testing_dir))
    print('zip done')



if __name__ == '__main__':
    #generator_runner(100)
    compile_and_execute()
    move_and_compress()

