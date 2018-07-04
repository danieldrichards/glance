'''
-------------------------------------
create_report.py

The basic structure is as follows:
  * Each type of hardware has its own method
    typically this means callng one large command and spliting it a ton.
  * This data are stored in a dictionary and returned.
  * Each of these hardware types are inserted into the larger system.
  * The resulting dictionary is written to a file in ./reports/<network name>/

    by Daniel Richards (ddrichar@ucsc.edu)
       on 6-23-2018

P.S. After working with files whose naming conventions I wouldn't wish on my
worst enemy, I wrote these programs with VERY specific naming.  
--------------------------------------
'''
from plumbum import local
from plumbum.cmd import echo, nslookup, sudo
from operator import itemgetter
import yaml
import copy
import json
import datetime
import os
import sys
import re
import csv

hostname = ''
network = ''

def double_split(start, end, string_cmd):
    try:
        return string_cmd.split(start)[1].split(end)[0].encode("ascii").strip()
    except:
        return ' '

def format_table(dic):
      output = {}
      for k, v in dic.iteritems():
            new_key = k.title() if len(k) > 3 else k.upper()
            while type(v) == str and '  ' in v:
                      v = v.replace('  ', ' ')
            output[new_key] = v
      #print output
      return output

def add_tree_specific_fields(array_dic):
      output = copy.deepcopy(array_dic)
      for entry in output:
          tooltip = []
          for k, v in entry.iteritems():
            if k != 'children':
                tooltip.append(str(k) + ": " + str(v))
          entry["tt_info"] = tooltip
      return output



def get_nics():
      inters = local["ls"]("/sys/class/net").encode("ascii")
      interfaces =  inters.split('\n')
      nic_array = []

      for i in interfaces[:-1]:
              output = local['ifconfig'](i).encode('ascii')
              nic_fields = {}

              nic_fields['IP'] = double_split('inet addr:', '  ', output)
              #print nic_fields["IP"]
              if nic_fields['IP'] != ' ':
                      try:
                          dns_lookup = nslookup(nic_fields["IP"])
                      
                          dns_server_name = double_split("= ", ".\n", dns_lookup)
                          nic_fields["DNS Server"] = dns_server_name
                      except:
                          pass
              nic_fields['MAC'] = double_split('HWaddr ', '  \n', output)
              try:
                  nic_fields['Speed'] = local['cat']('/sys/class/net/'+ i +'/speed').encode("ascii").strip()
              except:
                  nic_fields['Speed'] = "0"
              nic_array.append(nic_fields)

      return  {"NICs": nic_array}, nic_array, {"Name": "NICs", "children": add_tree_specific_fields(nic_array)}
            
def get_gpus():
      gpu_count = local["lspci"]().count("VGA") #BEWARE this doesn't reflect true gpu count remember the ASPEED device in lspci
      gpu_array = []
      if gpu_count == 1:
        return [],[],[]
      for gpu_num in range(0, gpu_count-1):
            gpu_fields = {}
            arg_arr = ['-i', str(gpu_num),
                       '--query-gpu=gpu_name,gpu_bus_id,vbios_version,serial,memory.total',
                       '--format=csv,noheader,nounits']
            gpu_info = local.get("nvidia-smi").run(arg_arr)[1].encode("ascii")
         
            gpu_arr = gpu_info.strip().split(", ")
            gpu_fields["Name"] = gpu_arr[0]
            gpu_fields['PCIID'] = gpu_arr[1]
            gpu_fields['Vios Version'] = gpu_arr[2]
            gpu_fields['Serial'] = gpu_arr[3]
            gpu_fields['Memory'] = gpu_arr[4]

            gpu_array.append(gpu_fields)
         
      return  {"GPUs": gpu_array}, gpu_array, {"Name": "GPUs", "children": add_tree_specific_fields(gpu_array)}

def get_cpus():
      
      cpu_fields = {}
      cpu_array = []
      cpu_info = local["lscpu"]().encode("ascii")
      soc_count = int(double_split("Socket(s):", "\n", cpu_info))

      cpu_fields["Model"] = double_split("Model name:", "\n", cpu_info)
      cpu_fields["Name"] = cpu_fields["Model"]
      cpu_fields["Cores"] = int(double_split("CPU(s):", "\n", cpu_info))/soc_count
      cpu_fields["Clock"] = int(float(double_split("CPU max MHz:", "\n", cpu_info)))
      cpu_fields["Architecture"] = double_split("Architecture:", "\n", cpu_info)
      cpu_fields["Threads Per Core"] = double_split("Thread(s) per core:", "\n", cpu_info)

      for soc in range(soc_count):
            cpu_fields["Socket"] = soc
            cpu_array.append(cpu_fields.copy())
     
      return  {"CPUs": cpu_array}, cpu_array, {"Name": "CPUs", "children": add_tree_specific_fields(cpu_array)}

def get_mem():
      mem_fields = {}
      mem_info = local["cat"]("/proc/meminfo")
      mem_number = double_split("MemTotal:", "\n", mem_info)
      mem_info = {"Total": mem_number}
      return {"Memory": copy.deepcopy(mem_info)}, copy.deepcopy(mem_info), {"Name": "Memory", "tt_info": "Total: " + mem_number}

def get_disks():
      global hostname
      if 'h' in hostname: #Head nodes dont have megacli >:(
          return [], [], []

      all_disks =  []
      try:
        all_disks = sudo["/usr/local/sbin/megacli"]('-pdlist -a0').split("\n\n")
      except:
        all_disks = sudo["/usr/local/bin/megacli"]('-pdlist -a0').split("\n\n")      
      disk_array = []
      
      for x in all_disks[:-1]:
          if "Port status: Active" in x and "Media Type: Hard Disk Device" in x:
              try:
                    disk_fields = {}
                    disk_fields["DiskID"] = double_split("evice Id:", "\n", x)
                    disk_fields["Name"] = "Disk: " + disk_fields["DiskID"]
                    disk_fields["Firmware"] = double_split("Firmware Level:", "\n", x)
                    disk_fields["Size"] = double_split("Raw Size:", "\n", x)
                    disk_fields["Serial"] = double_split("Inquiry Data: ", "\n", x)
    
                    disk_array.append(disk_fields)
              except:
                     print "\n\nERROR IN DISK READ\n"

      return {"Disks": disk_array}, disk_array, {"Name": "Disks", "children": add_tree_specific_fields(disk_array)}

def get_sys():
      global hostname 
      global network
      sys_fields = {}
      hostname = local["hostname"]().encode("ascii").strip()
      sys_fields["Hostname"] = hostname
      sys_fields["Bios Version"] = double_split("Version:", "\n", sudo["dmidecode"]())
      sys_fields["Vendor"] = double_split("Vendor:", "\n", sudo["dmidecode"]())
      network = local["/home/obs/bin/whereami"]().encode("ascii").strip().title()
      if(network == 'gbt'):
          network = network.upper()
      #observatory[0] = network
      sys_fields["Network"] = network

      task_type = ''
      if 'c' in hostname:    # I know, not elegant
            task_type = 'COMPUTE'
      elif 'h' in hostname:
            task_type = 'HEAD'
      else:
            task_type = 'STORAGE' 

      output =  {"Name": hostname, 'children': []}
      output.update(sys_fields)
      return output, sys_fields, copy.deepcopy(output)

def write_arr_to_csv(arr, hw_class):
  
 #print hostname
  #print "network: " + network
  if arr == None or len(arr) < 1:
   return
  if type(arr) != list:
      arr = [arr]
  list_rows = []
  for i in arr:
    i["Path"] = network + " --> " + hostname
    list_rows.append(format_table(i))
  filename = "csv_data/" + hw_class + '.csv'
  if os.path.exists(filename):
    append_write = 'a' # append if already exists
  else:
    append_write = 'w'

  with open(filename, 'a+') as f:  # Just use 'w' mode in 3.x
      w = csv.DictWriter(f, list_rows[0].keys())
      
      if append_write == 'w':
        w.writeheader()
      for r in list_rows:
        try:
            w.writerow(r)
        except:
          pass

# def make_pretty_yaml(sys_info, children_array):
#     sys = sys_info
#     for hardware in children_array:
#         print hardware
#         if len(hardware["children"]) > 0: # I don't want empty nodes e.g. GPU
#             sys[hardware["Name"]] = hardware["children"]
#     return sys




# def make_pretty_json(sys_info, children_array):
#     sys = sys_info
#     for hardware in children_array:
#         print hardware
#         if len(hardware["children"]) > 0: # I don't want empty nodes e.g. GPU
#             sys["children"].append({"Name": hardware["Name"], "children": add_tree_specific_fields(hardware["children"])})
#     return sys
def add_hardware(host, *args):
    if "children" not in host.keys():
        host["children"] = []
    for hw in args:
        if type(hw) == dict:
          print hw
        if hw:
          host["children"].append(hw)

sys_yaml, sys_csv, sys_tree = get_sys()


nic_yaml, nic_csv, nic_tree = get_nics()
gpu_yaml, gpu_csv, gpu_tree = get_gpus()

cpu_yaml, cpu_csv, cpu_tree = get_cpus()
mem_yaml, mem_csv, mem_tree = get_mem()

disk_yaml, disk_csv, disk_tree = get_disks()

add_hardware(sys_yaml, nic_yaml, gpu_yaml, cpu_yaml, mem_yaml, disk_yaml)

add_hardware(sys_tree, nic_tree, gpu_tree, cpu_tree, mem_tree, disk_tree)
##print "-------------------", sys_yaml["Hostname"]

today = str(datetime.date.today())
name  = hostname 
network = network

with open("reports/" + network +"/"+ name +'_'+ today +'.yaml', 'w') as outfile:
      yaml.dump({"device":sys_yaml}, outfile, default_flow_style=False)

with open("tree_data/"+ network +"/"+ name +'_'+ today + ".json", 'w') as outfile:
      json.dump(sys_tree, outfile, indent=4)


csvs = {"Memory": mem_csv, "CPUs": cpu_csv, "GPUs": gpu_csv, "NICs": nic_csv, "System": sys_csv}

for k,v in csvs.iteritems():
    write_arr_to_csv(v, k)
'''#sys_info_dict = get_sys()
copy_sys = sys_info_dict.copy()

yaml_data = make_pretty_yaml(sys_info_dict, [nic_info_dict, gpu_info_dict, cpu_info_dict, mem_info_dict])

with open("temp.yaml", 'w') as outfile:
      yaml.dump({"device":sys_info_dict}, outfile, default_flow_style=False)

json_data = make_pretty_json(sys_info_dict, [nic_info_dict, gpu_info_dict, cpu_info_dict, mem_info_dict])

with open("temp.json", 'w') as outfile:
      json.dump(json_data, outfile, indent=4)


sys_info_dict.update({"GPU(s)":gpu_info_dict})
sys_info_dict.update({"NICs":nic_info_dict})
sys_info_dict.update({"CPU":cpu_info_dict})
sys_info_dict.update({"Memory":mem_info_dict})
disk_info_dict = {}

if 'h' not in sys_info_dict['Hostname']: #Head nodes dont have megacli >:(
      disk_info_dict = get_disks()
      sys_info_dict.update({"Disks": disk_info_dict})



today = str(datetime.date.today())
name  = sys_info_dict["Hostname"] 
network = sys_info_dict["Network"]

with open("reports/" + network +"/"+ name +'_'+ today +'.yaml', 'w') as outfile:
      yaml.dump({"device" :sys_info_dict}, outfile, default_flow_style=False)


write_arr_to_csv(nic_info_dict, "NICs", network, name)
write_arr_to_csv(cpu_info_dict, "CPUs", network, name)
write_arr_to_csv(gpu_info_dict, "GPUs", network, name)
write_arr_to_csv(disk_info_dict, "Disks", network, name)
write_arr_to_csv(mem_info_dict, "Memory", network, name)
write_arr_to_csv(copy_sys, "SYS", network, name)
'''
